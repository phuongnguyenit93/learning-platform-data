# `ObjectInputFilter.Config.setSerialFilterFactory` và thời điểm cấu hình trong Java 17

`ObjectInputFilter.Config.setSerialFilterFactory(...)` cấu hình **factory lọc giải tuần tự hóa ở phạm vi toàn JVM**. Factory này quyết định bộ lọc nào được gắn vào từng `ObjectInputStream`, có thể kết hợp bộ lọc toàn cục, bộ lọc riêng của stream và chính sách theo ngữ cảnh đang chạy.

Điểm quan trọng nhất của API là **thời điểm gọi**: factory chỉ được cấu hình đúng một lần và phải được thiết lập **trước khi bất kỳ `ObjectInputStream` nào được tạo**. Nếu một thư viện hoặc framework đã tạo stream trước, lời gọi cấu hình trong ứng dụng có thể thất bại bằng `IllegalStateException`, ngay cả khi chưa có ai gọi `readObject()`.

Bài này tập trung vào API chính thức của Java 17, cách factory được gọi, thứ tự khởi tạo, cách kết hợp filter và cách chọn thời điểm cấu hình an toàn.

## 1. Vì sao Java cần filter factory?

Java Serialization có thể khôi phục object graph từ byte stream bằng `ObjectInputStream`. Trong quá trình đó, dữ liệu quyết định class nào được tạo, giá trị field và quan hệ tham chiếu giữa các object. Một số class có logic trong `readObject`, constructor hoặc callback giải tuần tự hóa; vì vậy đọc dữ liệu không đáng tin cậy có thể gây rủi ro bảo mật và tiêu thụ tài nguyên quá mức.

`ObjectInputFilter` cho phép kiểm soát:

- Class nào được phép hoặc bị từ chối.
- Độ sâu của object graph.
- Tổng số tham chiếu.
- Kích thước mảng.
- Số byte đã đọc từ stream.

Một filter trả về một trong ba trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| `ALLOWED` | Filter chấp nhận dữ liệu đang được kiểm tra |
| `REJECTED` | Filter từ chối; thao tác đọc bị dừng |
| `UNDECIDED` | Filter chưa quyết định; filter khác có thể tiếp tục đánh giá |

Nếu filter cuối cùng không từ chối, quá trình giải tuần tự hóa có thể tiếp tục. Vì vậy, `UNDECIDED` không tương đương với “từ chối”.

### 1.1. Ba thành phần cần phân biệt

| Thành phần | Vai trò | Phạm vi |
|---|---|---|
| **JVM-wide filter** | Chính sách lọc chung cho ứng dụng/process | Toàn JVM |
| **Stream-specific filter** | Chính sách bổ sung hoặc riêng cho một `ObjectInputStream` | Một stream |
| **Filter factory** | Chọn, kết hợp hoặc tạo filter hiệu lực cho từng stream | Toàn JVM |

Có thể hình dung:

```text
                         JVM
                          |
             setSerialFilterFactory(...)
                          |
                   Filter factory
                          |
              +-----------+-----------+
              |                       |
       ObjectInputStream A      ObjectInputStream B
              |                       |
       Filter hiệu lực A        Filter hiệu lực B
              |                       |
       đọc object graph A       đọc object graph B
              |                       |
       checkInput(...)          checkInput(...)
```

Factory là **bộ điều phối filter**. Nó không tự động định nghĩa class nào an toàn. Chính sách cho phép/từ chối vẫn phải được thể hiện trong các `ObjectInputFilter` mà factory lựa chọn hoặc kết hợp.

## 2. Chữ ký và phạm vi của setSerialFilterFactory

API Java 17:

```java
public static void setSerialFilterFactory(
        BinaryOperator<ObjectInputFilter> filterFactory
)
```

Các thành phần:

- `setSerialFilterFactory` là phương thức static của `ObjectInputFilter.Config`.
- `BinaryOperator<ObjectInputFilter>` nhận hai filter và trả về một filter.
- Đối số đầu tiên là filter hiện tại của stream.
- Đối số thứ hai là filter được yêu cầu ở lần gọi hiện tại.
- Giá trị trả về là filter sẽ được sử dụng cho stream.

Ví dụ tối thiểu:

```java
import java.io.ObjectInputFilter;
import java.util.function.BinaryOperator;

BinaryOperator<ObjectInputFilter> factory = (current, requested) -> {
    if (current == null) {
        return requested;
    }
    if (requested == null) {
        return current;
    }
    return ObjectInputFilter.merge(current, requested);
};

ObjectInputFilter.Config.setSerialFilterFactory(factory);
```

Factory này giữ filter hiện tại khi không có filter mới, giữ filter được yêu cầu nếu chưa có filter hiện tại, và kết hợp hai filter khi cả hai cùng tồn tại.

Đây chỉ là ví dụ về cách triển khai `BinaryOperator`. Trong ứng dụng thực tế, factory có thể cần nhận diện ngữ cảnh, áp dụng allow-list hoặc kết hợp thêm filter theo thread, module, thư viện hay class loader.

### 2.1. Factory là cấu hình toàn JVM

`setSerialFilterFactory` không nhận `ObjectInputStream` cụ thể và không cấu hình riêng một class. Nó thiết lập một factory dùng chung trong tiến trình Java.

Vì vậy:

- Một JVM chỉ có một filter factory đang hoạt động.
- Các `ObjectInputStream` được tạo trong JVM sử dụng factory đó.
- Không thể gọi phương thức để thay factory tùy ý theo từng request.
- Muốn có filter khác nhau cho từng stream, factory phải tự chọn filter dựa trên ngữ cảnh hoặc filter được yêu cầu.

Đây là lý do JEP 415 giới thiệu filter factory: một ứng dụng có thể gồm nhiều thư viện hoặc execution context, mỗi nơi cần tập class được phép giải tuần tự hóa khác nhau.

## 3. Quy tắc quan trọng nhất: cấu hình trước khi tạo ObjectInputStream

`setSerialFilterFactory` phải được gọi trước khi **bất kỳ instance `ObjectInputStream` nào được tạo**.

Ví dụ đúng:

```java
public class Application {
    public static void main(String[] args) {
        ObjectInputFilter.Config.setSerialFilterFactory(
                (current, requested) -> {
                    if (current == null) {
                        return requested;
                    }
                    if (requested == null) {
                        return current;
                    }
                    return ObjectInputFilter.merge(current, requested);
                }
        );

        startApplication();
    }

    private static void startApplication() {
        // Khởi tạo framework, service và các thành phần khác
        // sau khi factory đã được cấu hình.
    }
}
```

Lời gọi cấu hình được thực hiện ở đầu quá trình khởi động, trước khi các thành phần khác có cơ hội tạo `ObjectInputStream`.

### 3.1. Không đợi tới lúc readObject mới cấu hình

Ví dụ sai về thứ tự:

```java
ObjectInputStream input = new ObjectInputStream(source);

// Quá muộn: constructor phía trên đã tạo ObjectInputStream.
ObjectInputFilter.Config.setSerialFilterFactory(factory);

Object value = input.readObject();
```

Lỗi không phụ thuộc vào việc `readObject` đã được gọi hay chưa. Chỉ cần một `ObjectInputStream` đã được tạo là điều kiện cấu hình bằng phương thức này không còn được đáp ứng.

Điều này cũng áp dụng khi stream được tạo bởi thư viện bên thứ ba. Ứng dụng có thể chưa trực tiếp gọi `new ObjectInputStream(...)` nhưng một framework, thư viện cache, RPC hoặc thành phần khác đã tạo stream trước đó.

### 3.2. Chỉ được cấu hình đúng một lần

Factory có thể được cấu hình bằng đúng một trong các cách:

1. Gọi `ObjectInputFilter.Config.setSerialFilterFactory` trong mã.
2. Đặt system property `jdk.serialFilterFactory` khi khởi chạy JVM.
3. Đặt Security property `jdk.serialFilterFactory` trong file cấu hình bảo mật của JDK.

Sau khi factory đã được cấu hình, không thể thay bằng một factory khác. Nếu đã cấu hình qua system property hoặc Security property, ứng dụng cũng không thể ghi đè bằng `setSerialFilterFactory`.

```java
ObjectInputFilter.Config.setSerialFilterFactory(factoryA);

// Lỗi trạng thái: không thể thay bằng factoryB.
ObjectInputFilter.Config.setSerialFilterFactory(factoryB);
```

Lần gọi thứ hai có thể ném `IllegalStateException`.

### 3.3. Lỗi khi cấu hình quá muộn

Nếu built-in factory đã bị thay thế hoặc một `ObjectInputStream` đã được tạo, lời gọi:

```java
ObjectInputFilter.Config.setSerialFilterFactory(factory);
```

sẽ ném `IllegalStateException`.

Không có API công khai để “mở khóa”, thay factory hoặc khôi phục trạng thái trước khi tạo stream. Cách xử lý đúng là cấu hình ở lần khởi động tiếp theo, trước khi thành phần nào tạo stream.

### 3.4. Thời điểm khởi tạo Config cũng quan trọng

`ObjectInputFilter.Config` đọc các property liên quan khi class được khởi tạo:

- `jdk.serialFilter` dùng để cấu hình filter JVM-wide.
- `jdk.serialFilterFactory` dùng để chỉ định class factory JVM-wide.

Đặt property bằng `System.setProperty` sau khi `ObjectInputFilter.Config` đã được khởi tạo **không cấu hình lại** filter hoặc factory.

Ví dụ không có tác dụng như mong đợi:

```java
// Có thể Config đã được khởi tạo trước dòng này.
System.setProperty(
        "jdk.serialFilterFactory",
        "com.example.security.MyFilterFactory"
);
```

Nếu chọn cấu hình qua property, hãy đặt property ở thời điểm khởi chạy JVM:

```bash
java -Djdk.serialFilterFactory=com.example.security.MyFilterFactory \
     -m com.example.app/com.example.app.Main
```

Cách này cho phép JVM biết factory ngay từ giai đoạn khởi tạo, trước khi mã ứng dụng bắt đầu tạo stream.

## 4. Điều gì xảy ra khi factory được gọi?

Factory không được gọi cho mỗi object. Nó được gọi ở hai thời điểm liên quan đến cấu hình một `ObjectInputStream`:

1. Khi constructor `ObjectInputStream` được gọi.
2. Khi ứng dụng gọi `ObjectInputStream.setObjectInputFilter` để yêu cầu filter riêng cho stream.

Sau khi filter hiệu lực được chọn, `ObjectInputFilter.checkInput(...)` mới được gọi trong quá trình đọc object graph.

### 4.1. Lần gọi thứ nhất: constructor ObjectInputStream

Khi một stream được tạo, factory nhận:

| Tham số | Giá trị |
|---|---|
| `current` | `null` |
| `requested` | Filter JVM-wide đã cấu hình, hoặc `null` nếu chưa có |

Ví dụ:

```java
ObjectInputFilter.Config.setSerialFilter(globalFilter);

// Factory được gọi trong constructor.
ObjectInputStream input = new ObjectInputStream(source);
```

Ở lần gọi này, factory có thể chọn filter toàn cục, thêm filter theo context hoặc kết hợp nhiều filter để tạo filter ban đầu cho stream.

### 4.2. Lần gọi thứ hai: setObjectInputFilter

Sau khi tạo stream, ứng dụng có thể yêu cầu một filter riêng:

```java
try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(streamFilter);

    Object value = input.readObject();
}
```

Factory được gọi lần nữa với:

| Tham số | Giá trị |
|---|---|
| `current` | Filter hiện đang được gắn trên stream sau constructor |
| `requested` | Filter truyền vào `setObjectInputFilter` |

Factory quyết định filter hiệu lực mới. Nếu muốn giữ chính sách toàn cục và thêm chính sách riêng cho stream, factory cần kết hợp chúng đúng cách.

### 4.3. Factory không chạy trong từng lần checkInput

Quy trình tổng thể:

```text
Application startup
       |
       v
setSerialFilterFactory(factory)
       |
       v
new ObjectInputStream(...)
       |
       | factory.apply(null, globalFilter)
       v
Filter ban đầu của stream
       |
       +---- setObjectInputFilter(streamFilter)
       |          |
       |          | factory.apply(current, streamFilter)
       |          v
       |     Filter hiệu lực mới
       |
       v
readObject() / readUnshared()
       |
       v
ObjectInputFilter.checkInput(FilterInfo)
       |
       v
ALLOWED / REJECTED / UNDECIDED
```

Phân biệt rõ:

- `apply(current, requested)` của factory chọn filter cho stream.
- `checkInput(filterInfo)` của filter kiểm tra class và giới hạn tài nguyên khi giải tuần tự hóa.

## 5. Vai trò của filter JVM-wide và stream-specific filter

`setSerialFilterFactory` thường được dùng cùng hai loại filter khác.

### 5.1. JVM-wide filter

JVM-wide filter áp dụng ở cấp tiến trình. Có thể cấu hình bằng:

- System property `jdk.serialFilter` lúc khởi chạy.
- Security property `jdk.serialFilter`.
- `ObjectInputFilter.Config.setSerialFilter(filter)`.

Ví dụ cấu hình giới hạn tài nguyên:

```java
ObjectInputFilter limits = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=10000;maxbytes=5000000"
);

ObjectInputFilter.Config.setSerialFilter(limits);
```

Filter trên giới hạn độ sâu graph, số tham chiếu và số byte. Nó **chưa phải allow-list class**; các class không bị giới hạn có thể vẫn cho kết quả `UNDECIDED`. Cần thêm chính sách class phù hợp với dữ liệu thực tế.

### 5.2. Stream-specific filter

Stream-specific filter được đặt bằng:

```java
input.setObjectInputFilter(streamFilter);
```

Nó phù hợp khi mỗi nguồn dữ liệu hoặc mỗi nghiệp vụ có tập class được phép khác nhau.

Ví dụ:

- Import file khách hàng chỉ đọc DTO khách hàng.
- Import cấu hình chỉ đọc các kiểu cấu hình được định nghĩa.
- Một thư viện xử lý message chỉ đọc các kiểu message thuộc hợp đồng của nó.

Filter riêng phải được đặt **trước khi đọc object đầu tiên**. Theo API, `setObjectInputFilter` chỉ được gọi một lần cho mỗi stream.

### 5.3. Built-in factory mặc định làm gì?

Nếu ứng dụng không tự cấu hình factory, Java dùng built-in filter factory tương thích với hành vi cũ:

- Khi tạo `ObjectInputStream`, filter JVM-wide được gắn làm filter ban đầu.
- Khi gọi `setObjectInputFilter`, filter được yêu cầu sẽ thay thế filter JVM-wide theo hành vi mặc định, trừ trường hợp filter đã được đặt theo quy tắc API.

Điều này có nghĩa built-in factory **không tự động kết hợp** filter toàn cục và filter riêng của stream.

Nếu cần chính sách kết hợp, ví dụ filter toàn cục giới hạn tài nguyên và filter riêng giới hạn class, hãy cung cấp custom factory để quyết định cách ghép.

## 6. Quy tắc current và requested

Factory nhận hai tham số kiểu `ObjectInputFilter`:

```java
ObjectInputFilter apply(
        ObjectInputFilter current,
        ObjectInputFilter requested
);
```

Có thể gặp các trường hợp sau:

| `current` | `requested` | Ý nghĩa |
|---|---|---|
| `null` | Filter toàn cục | Lần gọi từ constructor stream |
| `null` | `null` | Chưa có filter toàn cục và chưa có filter hiện tại |
| Filter A | Filter B | Đang yêu cầu thêm/thay đổi filter riêng cho stream |
| Filter A | `null` | Không có filter mới; cần giữ filter hiện tại |

Factory cần xử lý được `null` ở cả hai tham số. Không nên viết code mặc định giả định cả hai luôn khác null.

### 6.1. Không được bỏ filter hiện tại bằng cách trả null

Nếu `current` khác `null`, factory phải trả về filter khác `null`. Quy tắc này ngăn việc vô tình vô hiệu hóa một filter đã được gắn.

Ví dụ sai:

```java
BinaryOperator<ObjectInputFilter> unsafeFactory =
        (current, requested) -> requested;
```

Nếu `current` đang có filter nhưng `requested` là `null`, factory trả `null`. Điều đó vi phạm quy tắc và có thể gây `IllegalStateException`.

Cách giữ filter hiện tại:

```java
BinaryOperator<ObjectInputFilter> safeFactory = (current, requested) -> {
    if (current != null && requested == null) {
        return current;
    }

    if (current == null) {
        return requested;
    }

    return ObjectInputFilter.merge(current, requested);
};
```

Ví dụ này thể hiện nguyên tắc bảo toàn filter. Factory thực tế có thể cần thêm xử lý theo context và chính sách class.

## 7. Kết hợp filter bằng ObjectInputFilter.merge

Java 17 cung cấp:

```java
ObjectInputFilter.merge(filterA, filterB)
```

Phương thức này trả về filter kết hợp kết quả của hai filter.

Quy tắc kết hợp:

1. Nếu một filter trả `REJECTED`, kết quả là `REJECTED`.
2. Nếu không filter nào từ chối và ít nhất một filter trả `ALLOWED`, kết quả là `ALLOWED`.
3. Nếu cả hai đều không quyết định, kết quả là `UNDECIDED`.

Bảng:

| Filter A | Filter B | Kết quả merge |
|---|---|---|
| `REJECTED` | `ALLOWED` | `REJECTED` |
| `REJECTED` | `UNDECIDED` | `REJECTED` |
| `ALLOWED` | `UNDECIDED` | `ALLOWED` |
| `ALLOWED` | `ALLOWED` | `ALLOWED` |
| `UNDECIDED` | `UNDECIDED` | `UNDECIDED` |

### 7.1. Merge không phải phép giao của hai allow-list

Đây là điểm rất dễ hiểu nhầm.

Nếu filter A cho `ALLOWED` và filter B cho `UNDECIDED`, kết quả là `ALLOWED`. Vì vậy `merge` không yêu cầu cả hai filter phải đồng ý mới cho phép class.

Tuy nhiên, `REJECTED` luôn thắng. Một filter có thể từ chối class bất kể filter còn lại chấp nhận.

Nếu thiết kế yêu cầu một class phải được mọi allow-list chấp nhận, cần viết logic kết hợp phù hợp với chính sách đó; không mặc định `merge` có nghĩa “A và B đều cho phép”.

### 7.2. UNDECIDED có thể dẫn tới chấp nhận

Trong cơ chế serialization filter, nếu filter không trả `REJECTED` thì quá trình có thể tiếp tục. Vì vậy, một filter chỉ từ chối một vài class và trả `UNDECIDED` cho mọi class còn lại không phải allow-list chặt.

Có thể dùng `ObjectInputFilter.rejectUndecidedClass(filter)` khi chính sách là chỉ chấp nhận class được allow rõ ràng:

```java
ObjectInputFilter strictAllowList =
        ObjectInputFilter.rejectUndecidedClass(classFilter);
```

Phương thức này chuyển kết quả `UNDECIDED` thành `REJECTED` cho class theo quy tắc API, với xử lý đặc biệt cho primitive và array. Chỉ dùng khi filter đầu vào thực sự được thiết kế theo mô hình allow-list.

## 8. Ví dụ factory tối thiểu: kết hợp filter hiện tại và filter mới

Một factory đơn giản có thể viết như sau:

```java
import java.io.ObjectInputFilter;
import java.util.function.BinaryOperator;

public final class MergingFilterFactory
        implements BinaryOperator<ObjectInputFilter> {

    public MergingFilterFactory() {
    }

    @Override
    public ObjectInputFilter apply(
            ObjectInputFilter current,
            ObjectInputFilter requested
    ) {
        if (current == null) {
            return requested;
        }

        if (requested == null) {
            return current;
        }

        return ObjectInputFilter.merge(current, requested);
    }
}
```

Đăng ký ở đầu chương trình:

```java
public class Main {
    public static void main(String[] args) {
        ObjectInputFilter.Config.setSerialFilterFactory(
                new MergingFilterFactory()
        );

        runApplication();
    }

    private static void runApplication() {
        // Khởi động phần còn lại của ứng dụng.
    }
}
```

Đặc điểm:

- Factory xử lý đúng trường hợp tham số null.
- Filter hiện tại được giữ lại khi không có filter mới.
- Nếu có hai filter, chúng được kết hợp bằng quy tắc của `ObjectInputFilter.merge`.
- Nếu filter hiện tại khác null, kết quả không bị chuyển thành null.

Đây là factory minh họa cho cách kết hợp cơ bản. Nó chưa chọn filter riêng theo người dùng, thread hoặc loại dữ liệu.

## 9. Ví dụ factory theo ngữ cảnh ThreadLocal

JEP 415 cho phép factory sử dụng thông tin ngoài hai tham số, chẳng hạn thread-local context, call stack, module hoặc class loader.

Một trường hợp thực tế: cùng một JVM có nhiều nghiệp vụ import. Mỗi nghiệp vụ cần allow-list riêng. Ứng dụng có thể đặt filter theo thread trước khi tạo `ObjectInputStream`; factory đọc filter đó và kết hợp với filter toàn cục.

Ví dụ:

```java
import java.io.ObjectInputFilter;
import java.util.concurrent.Callable;
import java.util.function.BinaryOperator;

public final class ContextFilterFactory
        implements BinaryOperator<ObjectInputFilter> {

    private static final ThreadLocal<ObjectInputFilter> CONTEXT_FILTER =
            new ThreadLocal<>();

    public ContextFilterFactory() {
    }

    @Override
    public ObjectInputFilter apply(
            ObjectInputFilter current,
            ObjectInputFilter requested
    ) {
        if (current == null) {
            return merge(requested, CONTEXT_FILTER.get());
        }

        return merge(current, requested);
    }

    private static ObjectInputFilter merge(
            ObjectInputFilter first,
            ObjectInputFilter second
    ) {
        if (first == null) {
            return second;
        }

        if (second == null) {
            return first;
        }

        return ObjectInputFilter.merge(first, second);
    }

    public static <T> T withFilter(
            ObjectInputFilter filter,
            Callable<T> action
    ) throws Exception {
        ObjectInputFilter previous = CONTEXT_FILTER.get();

        try {
            if (filter == null) {
                CONTEXT_FILTER.remove();
            } else {
                CONTEXT_FILTER.set(filter);
            }

            return action.call();
        } finally {
            if (previous == null) {
                CONTEXT_FILTER.remove();
            } else {
                CONTEXT_FILTER.set(previous);
            }
        }
    }
}
```

Đăng ký factory một lần trong bootstrap:

```java
ObjectInputFilter.Config.setSerialFilterFactory(
        new ContextFilterFactory()
);
```

Sau đó, khi cần đọc một loại dữ liệu:

```java
ObjectInputFilter importFilter = info -> {
    Class<?> type = info.serialClass();

    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == ImportRecord.class || type == String.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};

Object value = ContextFilterFactory.withFilter(
        importFilter,
        () -> {
            try (ObjectInputStream input =
                         new ObjectInputStream(source)) {
                return input.readObject();
            }
        }
);
```

Trong ví dụ:

1. `withFilter` đặt chính sách import vào ThreadLocal.
2. `new ObjectInputStream` gọi factory.
3. Factory nhận filter JVM-wide qua `requested` và lấy thêm filter theo thread.
4. Factory kết hợp hai filter thành filter của stream.
5. Sau khi constructor hoàn tất, filter đã gắn vào stream; việc dọn ThreadLocal trong `finally` không xóa filter đang gắn.
6. Khi `readObject` đọc dữ liệu, filter hiệu lực kiểm tra class và giới hạn tài nguyên.

Filter minh họa chỉ cho phép hai class cụ thể. Ứng dụng thật phải liệt kê đầy đủ kiểu dữ liệu hợp lệ, bao gồm kiểu trong object graph như collection hoặc các kiểu hỗ trợ cần thiết. Không dùng ví dụ này như allow-list hoàn chỉnh cho mọi ứng dụng.

### 9.1. Vì sao phải khôi phục ThreadLocal trong finally?

Ứng dụng server thường dùng thread pool. Nếu chỉ gọi `ThreadLocal.set` mà không khôi phục hoặc xóa giá trị, request tiếp theo có thể chạy trên cùng thread và vô tình nhận filter của request trước.

Mẫu `try/finally` trong ví dụ giữ lại giá trị trước đó và phục hồi sau khi tác vụ hoàn thành. Đây là nguyên tắc quan trọng khi dùng context theo thread.

Với xử lý bất đồng bộ hoặc chuyển thread, `ThreadLocal` không tự truyền context sang thread khác. Hãy dùng cơ chế truyền context phù hợp với kiến trúc ứng dụng.

## 10. Cấu hình factory bằng system property

Nếu muốn cấu hình từ lúc JVM khởi chạy thay vì gọi API trong mã, dùng:

```bash
java -Djdk.serialFilterFactory=com.example.security.MyFilterFactory \
     -jar application.jar
```

Giá trị property là **tên đầy đủ của class factory**, không phải tên method hoặc biểu thức lambda.

Class factory được JVM nạp trong giai đoạn khởi tạo cấu hình và phải:

- Là class `public`.
- Có constructor không tham số và `public`.
- Implement `BinaryOperator<ObjectInputFilter>`.
- Có thể được truy cập qua application class loader.
- Cung cấp implementation của `apply`.

Ví dụ khung class:

```java
package com.example.security;

import java.io.ObjectInputFilter;
import java.util.function.BinaryOperator;

public final class MyFilterFactory
        implements BinaryOperator<ObjectInputFilter> {

    public MyFilterFactory() {
    }

    @Override
    public ObjectInputFilter apply(
            ObjectInputFilter current,
            ObjectInputFilter requested
    ) {
        if (current == null) {
            return requested;
        }
        if (requested == null) {
            return current;
        }
        return ObjectInputFilter.merge(current, requested);
    }
}
```

Khi factory được chỉ định bằng property, ứng dụng không gọi thêm `setSerialFilterFactory` để thay factory. Cấu hình từ property không thể bị ứng dụng ghi đè bằng lời gọi này.

### 10.1. Security property

Có thể đặt `jdk.serialFilterFactory` trong file Security của JDK. Cách này thích hợp khi muốn áp dụng factory theo cấu hình runtime cho các ứng dụng dùng JDK đó.

System property có độ ưu tiên cao hơn Security property cùng tên. Nếu cả hai cùng được đặt, system property được dùng.

### 10.2. System.setProperty không thay thế cấu hình lúc khởi động

Không nên làm:

```java
System.setProperty(
        "jdk.serialFilterFactory",
        "com.example.security.MyFilterFactory"
);
```

rồi mong JVM nạp factory ngay sau đó. Property này được đọc khi `ObjectInputFilter.Config` khởi tạo; thay đổi sau thời điểm đó không cài đặt hoặc thay thế factory.

Nếu cần cấu hình động theo ứng dụng, gọi `setSerialFilterFactory` đúng một lần ở bootstrap, trước mọi `ObjectInputStream`.

## 11. Phân biệt setSerialFilter và setSerialFilterFactory

Hai API có tên gần giống nhưng nhiệm vụ khác nhau:

| API | Nhận vào | Chức năng |
|---|---|---|
| `Config.setSerialFilter(filter)` | Một `ObjectInputFilter` | Đặt filter JVM-wide |
| `Config.setSerialFilterFactory(factory)` | Một `BinaryOperator<ObjectInputFilter>` | Đặt factory lựa chọn/kết hợp filter cho từng stream |
| `ObjectInputStream.setObjectInputFilter(filter)` | Một `ObjectInputFilter` | Yêu cầu filter riêng cho một stream |

Ví dụ chỉ cần chính sách toàn cục đơn giản:

```java
ObjectInputFilter globalFilter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=20;maxrefs=10000;maxbytes=5000000"
        );

ObjectInputFilter.Config.setSerialFilter(globalFilter);
```

Trường hợp này thường không cần custom factory. Built-in factory mặc định sẽ gắn filter toàn cục cho stream mới.

Nếu muốn mỗi stream có filter khác nhau và cần kết hợp chúng với chính sách toàn cục, mới cân nhắc `setSerialFilterFactory`.

### 11.1. getSerialFilterFactory trả về gì?

```java
BinaryOperator<ObjectInputFilter> factory =
        ObjectInputFilter.Config.getSerialFilterFactory();
```

Phương thức này trả factory đang hoạt động. Nếu ứng dụng chưa cấu hình factory riêng, kết quả vẫn là built-in factory của JDK.

Do đó, `getSerialFilterFactory()` trả về một đối tượng không có nghĩa ứng dụng đã cài custom factory.

Tương tự:

```java
ObjectInputFilter filter =
        ObjectInputFilter.Config.getSerialFilter();
```

có thể trả `null` nếu chưa có JVM-wide filter.

## 12. Factory được gọi khi nào, filter được gọi khi nào?

Cần phân biệt lifecycle của factory với lifecycle của filter.

| Thao tác | Thành phần được gọi | Mục đích |
|---|---|---|
| `setSerialFilterFactory` | Không gọi `apply` ngay để xử lý từng stream | Đăng ký factory toàn JVM |
| `new ObjectInputStream(...)` | `factory.apply(null, globalFilter)` | Chọn filter ban đầu |
| `setObjectInputFilter(filter)` | `factory.apply(current, requested)` | Chọn filter hiệu lực mới |
| `readObject()` / `readUnshared()` | `filter.checkInput(info)` | Kiểm tra dữ liệu đang giải tuần tự hóa |

Filter có thể được gọi nhiều lần khi đọc object graph. Factory không chạy cho mỗi class hay mỗi reference.

### 12.1. FilterInfo cung cấp thông tin gì?

Trong `checkInput`, `ObjectInputFilter.FilterInfo` cung cấp:

- `serialClass()`: class đang được kiểm tra, có thể là `null` khi chỉ kiểm tra metric.
- `arrayLength()`: độ dài mảng nếu phần tử đang xét là array.
- `depth()`: độ sâu object graph.
- `references()`: số tham chiếu đã đọc.
- `streamBytes()`: số byte đã đọc từ stream theo cách triển khai.

Ví dụ filter giới hạn tài nguyên:

```java
ObjectInputFilter limits = info -> {
    if (info.depth() > 20) {
        return ObjectInputFilter.Status.REJECTED;
    }

    if (info.references() > 10_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    if (info.streamBytes() > 5_000_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    if (info.arrayLength() > 100_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

Filter trên từ chối graph vượt giới hạn và trả `UNDECIDED` nếu không vượt. Nó không tự tạo allow-list class; cần kết hợp với chính sách class nếu muốn giới hạn loại object.

Một số dữ liệu như primitive và String được mã hóa trực tiếp trong stream có quy tắc gọi filter riêng; không nên giả định filter sẽ xác thực mọi giá trị field hoặc mọi nội dung chuỗi. Ứng dụng vẫn cần kiểm tra dữ liệu sau khi đọc theo hợp đồng nghiệp vụ.

## 13. Thời điểm cấu hình trong vòng đời ứng dụng

Một trình tự khởi động phù hợp:

1. JVM nhận system/security properties.
2. Ứng dụng bắt đầu chạy.
3. Ứng dụng cấu hình JVM-wide filter nếu cần.
4. Ứng dụng cấu hình custom filter factory nếu cần.
5. Framework và service được khởi tạo.
6. Các thành phần tạo `ObjectInputStream`.
7. Factory chọn filter cho từng stream.
8. Khi đọc dữ liệu, filter kiểm tra object graph.

Sơ đồ:

```text
JVM launch
   |
   +-- đọc -Djdk.serialFilter
   |
   +-- đọc -Djdk.serialFilterFactory
   |
   v
Application bootstrap
   |
   +-- setSerialFilter(...)        (nếu cấu hình bằng code)
   |
   +-- setSerialFilterFactory(...) (nếu cấu hình bằng code)
   |
   v
Khởi tạo framework / service
   |
   v
Tạo ObjectInputStream
   |
   v
Factory chọn filter
   |
   v
Đọc object và kiểm tra filter
```

### 13.1. Vì sao nên cấu hình trước khi khởi tạo framework?

Framework có thể tạo `ObjectInputStream` trong quá trình:

- Khởi tạo cache hoặc session store.
- Nạp cấu hình hoặc trạng thái đã serialize.
- Tạo kênh RPC hoặc cơ chế trao đổi object.
- Khởi tạo thư viện tích hợp có dùng Java Serialization.

Nếu ứng dụng đợi tới khi xử lý request đầu tiên mới cấu hình, có thể đã quá muộn.

Đặt factory trong bootstrap trung tâm giúp kiểm soát thứ tự rõ ràng. Nếu không kiểm soát được thời điểm class `ObjectInputFilter.Config` được khởi tạo hoặc stream đầu tiên được tạo, cấu hình bằng JVM property lúc khởi chạy là lựa chọn đáng tin cậy hơn.

## 14. Các lỗi thường gặp

| Lỗi hoặc triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `IllegalStateException` khi gọi `setSerialFilterFactory` | Factory đã được cấu hình hoặc một `ObjectInputStream` đã được tạo | Chuyển cấu hình về bootstrap hoặc dùng property lúc JVM khởi chạy |
| Factory không được nạp từ `System.setProperty` | Property được đặt sau khi `Config` đã khởi tạo | Dùng `-Djdk.serialFilterFactory` hoặc Security property |
| Lần gọi factory đầu có hai tham số null | Chưa có static filter và chưa có current filter | Factory phải xử lý null an toàn; có thể trả null nếu chính sách cho phép |
| Filter toàn cục bị thay bởi filter riêng | Built-in factory mặc định không tự merge hai filter | Cấu hình custom factory nếu cần kết hợp |
| Filter hiện tại biến mất | Factory trả null khi current khác null | Luôn bảo toàn current hoặc trả filter kết hợp khác null |
| Class không bị chặn dù filter trả UNDECIDED | Không có filter nào trả REJECTED | Dùng allow-list hoặc từ chối kết quả undecided theo chính sách |
| Class hợp lệ bị từ chối | Allow-list thiếu class phụ trợ trong object graph | Bổ sung đúng kiểu cần thiết, không mở rộng thành allow-all |
| Request sau dùng nhầm filter của request trước | ThreadLocal không được khôi phục | Dùng try/finally để khôi phục hoặc remove context |
| Factory chạy nhưng dữ liệu vẫn không an toàn | Factory chỉ chọn filter; chính sách filter quá rộng hoặc không có | Thiết kế allow-list và giới hạn tài nguyên cụ thể |

### 14.1. Factory trả null không có nghĩa là từ chối tất cả

`null` biểu thị stream không có filter hiệu lực. Nó không phải trạng thái `REJECTED`.

Nếu ứng dụng cần bảo vệ mọi stream, factory phải bảo đảm filter phù hợp được gắn cho từng stream. Đặc biệt, nếu không có static filter, không có context filter và factory trả null, stream có thể không được lọc.

### 14.2. Không cho phép tất cả class chỉ để tránh lỗi

Một filter kiểu:

```java
info -> ObjectInputFilter.Status.ALLOWED
```

cho phép mọi class và bỏ mất mục tiêu hạn chế deserialization. Chỉ sử dụng allow-list theo các kiểu dữ liệu thực sự cần thiết và đặt giới hạn tài nguyên hợp lý.

### 14.3. Không xem factory là cơ chế xác thực dữ liệu

Filter kiểm soát class và một số metric của object graph. Nó không thay thế:

- Xác thực người gửi.
- Xác thực tính toàn vẹn hoặc chữ ký của dữ liệu.
- Kiểm tra giá trị field theo nghiệp vụ.
- Mã hóa dữ liệu khi truyền hoặc lưu.
- Việc tránh deserialize dữ liệu không đáng tin cậy.

Nếu có thể, ưu tiên định dạng dữ liệu có schema và parser an toàn thay cho Java native serialization đối với dữ liệu từ bên ngoài.

## 15. Ví dụ hoàn chỉnh: cấu hình factory ở bootstrap

Ví dụ dưới đây minh họa một ứng dụng có giới hạn toàn cục và filter theo từng nghiệp vụ.

### 15.1. Factory

```java
import java.io.ObjectInputFilter;
import java.util.function.BinaryOperator;

public final class ApplicationFilterFactory
        implements BinaryOperator<ObjectInputFilter> {

    public ApplicationFilterFactory() {
    }

    @Override
    public ObjectInputFilter apply(
            ObjectInputFilter current,
            ObjectInputFilter requested
    ) {
        if (current == null) {
            return requested;
        }

        if (requested == null) {
            return current;
        }

        return ObjectInputFilter.merge(current, requested);
    }
}
```

### 15.2. Bootstrap

```java
import java.io.ObjectInputFilter;

public final class Main {
    public static void main(String[] args) {
        ObjectInputFilter globalLimits =
                ObjectInputFilter.Config.createFilter(
                        "maxdepth=20;maxrefs=10000;maxbytes=5000000;maxarray=100000"
                );

        // Thiết lập chính sách giới hạn toàn JVM.
        ObjectInputFilter.Config.setSerialFilter(globalLimits);

        // Phải gọi trước khi bất kỳ ObjectInputStream nào được tạo.
        ObjectInputFilter.Config.setSerialFilterFactory(
                new ApplicationFilterFactory()
        );

        startServices();
    }

    private static void startServices() {
        // Khởi tạo service, framework và các thành phần khác.
    }
}
```

Ở ví dụ này, filter toàn cục giới hạn tài nguyên. Nó không giới hạn class vì pattern chỉ có các resource limit. Factory giữ filter đó khi stream được tạo và kết hợp filter riêng nếu stream yêu cầu.

Ứng dụng vẫn phải bổ sung chính sách class allow-list cho dữ liệu không đáng tin cậy. Giới hạn depth/bytes/array không đủ để xác định class nào an toàn.

### 15.3. Gắn filter riêng cho stream

```java
ObjectInputFilter streamFilter = ObjectInputFilter.Config.createFilter(
        "com.example.dto.**;java.base/*;!*"
);

try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(streamFilter);

    Object value = input.readObject();
}
```

Với custom factory ở trên, filter riêng được merge với filter hiện tại. Vì `merge` ưu tiên `REJECTED`, các giới hạn toàn cục hoặc quy tắc từ chối của filter hiện tại vẫn có thể chặn class.

Pattern minh họa cho phép package DTO và các class thuộc module `java.base`; đây vẫn là ví dụ cần điều chỉnh theo object graph thực tế. Không nên dùng package pattern quá rộng nếu dữ liệu chỉ cần một số kiểu cụ thể.

## 16. Khi nào nên dùng custom factory, khi nào không?

| Tình huống | Lựa chọn |
|---|---|
| Một ứng dụng chỉ cần giới hạn class và resource chung | JVM-wide filter với `setSerialFilter` hoặc property `jdk.serialFilter` |
| Mỗi stream cần allow-list khác nhau, không cần kết hợp filter toàn cục | Stream-specific filter; xem xét built-in factory behavior |
| Cần giữ global filter và kết hợp filter riêng của từng stream | Custom factory qua `setSerialFilterFactory` |
| Nhiều module/thư viện có context deserialization khác nhau | Custom factory chọn filter theo context |
| Cần cấu hình bắt buộc trước khi application code chạy | System/Security property `jdk.serialFilterFactory` |
| Ứng dụng đã tạo ObjectInputStream trước khi bootstrap hoàn tất | Không thể cài custom factory bằng phương thức sau đó; sửa thứ tự khởi động hoặc cấu hình ở lần chạy mới |

Không cần custom factory chỉ vì ứng dụng dùng `ObjectInputFilter`. Với chính sách đơn giản, JVM-wide filter và built-in factory mặc định thường đủ.

## 17. Bài tập tự luyện

### Bài 1 — Gọi factory ở thời điểm nào?

Ứng dụng tạo `ObjectInputStream` trong static initializer của một thư viện, sau đó mới gọi `setSerialFilterFactory` trong `main`.

**Đáp án:** Quá muộn. Constructor stream đã chạy trước và factory mặc định đã được sử dụng. Cần cấu hình trong JVM property hoặc bảo đảm factory được cài trước khi thư viện tạo stream.

### Bài 2 — Factory được gọi bao nhiêu lần?

Một stream được tạo và sau đó gọi `setObjectInputFilter` một lần. Factory được gọi ở những thời điểm nào?

**Đáp án:** Hai lần: một lần trong constructor `ObjectInputStream` và một lần trong `setObjectInputFilter`. Nó không được gọi cho mỗi object trong stream.

### Bài 3 — Hai tham số null có nghĩa gì?

Lần gọi đầu tiên có `current == null` và `requested == null`.

**Đáp án:** Chưa có filter hiện tại và cũng chưa có JVM-wide filter được truyền vào. Factory có thể trả null nếu ứng dụng thực sự cho phép stream không có filter, hoặc chọn filter mặc định của ứng dụng.

### Bài 4 — Vì sao factory không được trả null?

Stream đang có filter `current` khác null; lời gọi tiếp theo có `requested == null`. Factory trả null.

**Đáp án:** Vi phạm quy tắc không được thay filter hiện tại khác null bằng null. Factory cần trả current hoặc filter kết hợp khác null.

### Bài 5 — Merge có phải giao của hai allow-list?

Filter A trả `ALLOWED`; filter B trả `UNDECIDED`.

**Đáp án:** `ObjectInputFilter.merge` trả `ALLOWED`. Đây không phải phép giao của allow-list. Nếu một filter trả `REJECTED` thì kết quả luôn `REJECTED`.

### Bài 6 — setSerialFilterFactory có thay setSerialFilter không?

**Đáp án:** Không. `setSerialFilter` đặt một filter JVM-wide; `setSerialFilterFactory` đặt hàm chọn/kết hợp filter cho mỗi stream. Factory có thể nhận static filter như tham số `requested` ở lần gọi đầu.

### Bài 7 — Có thể cấu hình factory bằng System.setProperty trong main không?

**Đáp án:** Không nên. Property được đọc khi `ObjectInputFilter.Config` khởi tạo. Hãy dùng `-Djdk.serialFilterFactory` lúc khởi chạy JVM hoặc gọi `setSerialFilterFactory` sớm trong bootstrap trước mọi stream.

### Bài 8 — Factory đã chạy, vậy object đã được kiểm tra chưa?

**Đáp án:** Chưa. Factory chỉ chọn filter. `checkInput` của filter mới được gọi trong quá trình `readObject`/`readUnshared` để kiểm tra class và metric của object graph.

## 18. Ghi nhớ

- `ObjectInputFilter.Config.setSerialFilterFactory` cấu hình factory toàn JVM, không cấu hình một stream riêng lẻ.
- Factory chỉ được cấu hình đúng một lần bằng method, system property hoặc Security property.
- Khi dùng method, phải gọi trước khi bất kỳ `ObjectInputStream` nào được tạo.
- Lời gọi factory xảy ra trong constructor `ObjectInputStream` và khi `setObjectInputFilter` được gọi.
- Factory không chạy cho từng object; `ObjectInputFilter.checkInput` mới kiểm tra dữ liệu khi giải tuần tự hóa.
- Lần gọi đầu có `current == null`; `requested` là JVM-wide filter hoặc null.
- Nếu `current` khác null, factory phải trả filter khác null.
- Built-in factory mặc định gắn JVM-wide filter khi tạo stream; stream-specific filter thay thế filter đó theo hành vi mặc định.
- Dùng custom factory khi cần kết hợp global filter, stream filter và context-specific filter.
- `ObjectInputFilter.merge` ưu tiên REJECTED, sau đó ALLOWED, cuối cùng mới UNDECIDED; nó không phải phép giao allow-list.
- `System.setProperty` sau khi Config khởi tạo không cấu hình lại factory.
- Factory không tự tạo chính sách bảo mật; ứng dụng phải cung cấp allow-list và giới hạn tài nguyên phù hợp.
- Tránh deserialize dữ liệu không đáng tin cậy nếu có thể; serialization filter chỉ là một lớp phòng vệ.

## Tài liệu tham khảo chính thức cho Java 17

- [Java SE 17 API — `ObjectInputFilter.Config`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html).
- [Java SE 17 API — `ObjectInputFilter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html).
- [Java SE 17 API — `ObjectInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html).
- [Oracle Java 17 — Serialization Filtering](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html).
- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290).
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415).


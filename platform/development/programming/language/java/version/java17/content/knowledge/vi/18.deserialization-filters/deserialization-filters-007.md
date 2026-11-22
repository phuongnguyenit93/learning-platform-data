# Filter factory theo ngữ cảnh từ Java 17

Java Serialization có thể khôi phục một đồ thị object từ byte stream bằng `ObjectInputStream`. Nếu dữ liệu đến từ nguồn không đáng tin cậy, việc deserialization có thể kích hoạt logic trong các lớp được khôi phục và tiêu thụ tài nguyên lớn. Vì vậy, ứng dụng cần giới hạn những lớp được phép đọc và kích thước đồ thị object.

Java đã có `ObjectInputFilter` từ Java 9 để kiểm tra lớp và giới hạn tài nguyên trong quá trình deserialization. Tuy nhiên, một ứng dụng lớn có thể chứa nhiều thư viện hoặc nhiều luồng xử lý, mỗi nơi cần một tập lớp khác nhau. Một filter toàn JVM quá rộng sẽ khó đáp ứng mọi ngữ cảnh; filter riêng từng stream lại có thể vô tình thay thế chính sách toàn cục.

Java 17 bổ sung **filter factory theo ngữ cảnh** qua JEP 415. Factory quyết định filter nào sẽ gắn với mỗi `ObjectInputStream`, dựa trên filter hiện tại, filter được yêu cầu và thông tin ngữ cảnh như thread, call stack, module, thư viện hoặc class loader. Nhờ đó, ứng dụng có thể kết hợp chính sách chung với chính sách riêng cho từng luồng xử lý.

## 1. Vì sao cần filter factory?

Một filter kiểm soát hai nhóm điều kiện:

- **Loại dữ liệu:** class nào được phép hoặc bị từ chối khi đọc object.
- **Tài nguyên:** độ sâu đồ thị, số tham chiếu, kích thước mảng và số byte đã đọc.

Một hệ thống có thể có nhiều ngữ cảnh deserialization:

| Ngữ cảnh | Loại dữ liệu dự kiến |
| --- | --- |
| Đọc thông điệp nội bộ | DTO của module thông điệp và các kiểu hỗ trợ đã biết |
| Đọc cache | Các kiểu cache được ứng dụng kiểm soát |
| Đọc dữ liệu tương thích từ đối tác | Một tập lớp hẹp theo giao thức đối tác |
| Đọc trạng thái công việc | Các kiểu trạng thái và metadata của job |

Nếu tất cả dùng cùng một allow-list lớn, mỗi stream có thể đọc nhiều kiểu hơn mức cần thiết. Nếu mỗi thành phần tự gọi `setObjectInputFilter`, một thành phần có thể thay thế filter toàn JVM theo hành vi mặc định của Java.

Filter factory giải quyết việc **chọn hoặc kết hợp filter cho từng stream**. Factory không tự kiểm tra từng object; nó cung cấp `ObjectInputFilter` để `ObjectInputStream` gọi trong quá trình đọc.

## 2. ObjectInputFilter và ba trạng thái kết quả

`java.io.ObjectInputFilter` là functional interface. Filter nhận `FilterInfo` và trả về một trong ba trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `ALLOWED` | Filter xác nhận đối tượng/điều kiện được phép |
| `REJECTED` | Filter từ chối; deserialization bị dừng |
| `UNDECIDED` | Filter không đưa ra quyết định cho thông tin đó |

`UNDECIDED` không đồng nghĩa với từ chối. Nếu filter cuối cùng trả `UNDECIDED`, `ObjectInputStream` vẫn có thể tiếp tục deserialization. Vì vậy, khi xây dựng allow-list, cần bảo đảm các lớp không được liệt kê sẽ bị từ chối, thay vì để chúng ở trạng thái chưa quyết định.

### 2.1. Filter kiểm tra những thông tin nào?

`ObjectInputFilter.FilterInfo` cung cấp:

- `serialClass()`: class đang được kiểm tra; có thể là `null` khi lần kiểm tra chỉ liên quan đến số liệu đồ thị.
- `arrayLength()`: độ dài mảng nếu đối tượng là mảng, hoặc giá trị âm nếu không phải.
- `depth()`: độ sâu hiện tại của đồ thị object.
- `references()`: số tham chiếu object đã được đọc trong stream.
- `streamBytes()`: số byte đã tiêu thụ từ stream theo implementation.

Filter có thể kiểm tra một hoặc nhiều thông tin. Ví dụ:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter resourceFilter = info -> {
    if (info.depth() > 12
            || info.references() > 500
            || info.streamBytes() > 1_000_000
            || info.arrayLength() > 20_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
~~~

Ví dụ này chỉ giới hạn tài nguyên; nó không cho phép một class cụ thể. Nếu không có filter khác quyết định class, kết quả `UNDECIDED` không tạo thành allow-list. Trong ứng dụng thực tế, hãy kết hợp giới hạn tài nguyên với chính sách class rõ ràng.

### 2.2. Pattern filter

Java cung cấp `ObjectInputFilter.Config.createFilter(String)` để tạo filter từ chuỗi pattern:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=12;maxrefs=200;maxbytes=500000;maxarray=10000;"
        + "com.example.dto.Message;!*");
~~~

Các giới hạn phổ biến:

| Pattern | Ý nghĩa |
| --- | --- |
| `maxdepth=12` | Độ sâu đồ thị tối đa |
| `maxrefs=200` | Số tham chiếu tối đa |
| `maxbytes=500000` | Số byte tối đa được đọc |
| `maxarray=10000` | Độ dài mảng tối đa |

Các pattern lớp có thể chỉ định tên class, package hoặc module. Dấu `!` đứng trước pattern để từ chối lớp khớp. Dấu `*` và `**` có ý nghĩa khác nhau: `package.*` khớp lớp trực tiếp trong package, còn `package.**` bao gồm cả các package con. Pattern `!*` ở cuối từ chối mọi lớp không khớp các pattern cho phép trước đó.

Với allow-list, phần `!*` rất quan trọng. Nếu bỏ nó, lớp không khớp pattern có thể trả `UNDECIDED`, và trạng thái này không tự động có nghĩa là bị chặn.

## 3. Filter toàn JVM và filter riêng cho stream

Java có hai phạm vi filter:

**Static JVM-wide filter** áp dụng trong toàn bộ JVM. Có thể cấu hình bằng system property `jdk.serialFilter` lúc khởi chạy hoặc qua `ObjectInputFilter.Config.setSerialFilter(...)`.

**Stream-specific filter** gắn với một `ObjectInputStream` bằng `setObjectInputFilter(...)`.

Ví dụ cấu hình filter toàn JVM qua command line:

~~~bash
java -Djdk.serialFilter="maxdepth=20;maxrefs=1000;maxbytes=2000000;!com.example.legacy.UnsafeType" \
     -jar application.jar
~~~

Hoặc cấu hình trong code trước khi filter được thiết lập:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter globalFilter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=1000;maxbytes=2000000;"
        + "!com.example.legacy.UnsafeType");

ObjectInputFilter.Config.setSerialFilter(globalFilter);
~~~

`setSerialFilter` chỉ đặt filter toàn JVM nếu filter chưa được cấu hình hoặc thiết lập trước đó. Nếu filter đã được đặt bằng system property, Security property hoặc lời gọi API khác, việc đặt lại có thể ném `IllegalStateException`.

### 3.1. Hành vi của factory mặc định

Nếu ứng dụng không đăng ký factory riêng, `ObjectInputFilter.Config.getSerialFilterFactory()` trả về factory tích hợp sẵn. Factory này giữ hành vi tương thích với cách cấu hình filter trước Java 17:

1. Khi tạo `ObjectInputStream`, filter toàn JVM được dùng làm filter ban đầu của stream.
2. Khi gọi `setObjectInputFilter(...)`, filter được yêu cầu cho stream thay thế filter ban đầu theo hành vi mặc định.

Điểm thứ hai rất quan trọng: **filter riêng của stream không mặc định được ghép với filter toàn JVM**. Nếu ứng dụng muốn cả hai chính sách đều được áp dụng, cần một factory tùy chỉnh để kết hợp chúng.

## 4. Filter factory được gọi khi nào?

Factory có kiểu `BinaryOperator<ObjectInputFilter>` và được gọi ở hai thời điểm:

1. Khi tạo một `ObjectInputStream`.
2. Khi gọi `ObjectInputStream.setObjectInputFilter(...)` để đặt filter riêng cho stream.

Factory nhận hai tham số:

~~~java
ObjectInputFilter apply(
        ObjectInputFilter current,
        ObjectInputFilter requested)
~~~

Ý nghĩa của hai tham số:

| Tham số | Khi tạo stream | Khi gọi setObjectInputFilter |
| --- | --- | --- |
| `current` | `null` | Filter hiện đang gắn với stream |
| `requested` | Filter static JVM-wide | Filter được truyền vào `setObjectInputFilter` |

Factory trả về filter cuối cùng sẽ gắn với stream.

Sơ đồ:

~~~text
new ObjectInputStream(...)
        |
        v
Factory.apply(null, globalFilter)
        |
        v
Chọn filter ban đầu cho stream
        |
        v
setObjectInputFilter(streamFilter)
        |
        v
Factory.apply(currentFilter, streamFilter)
        |
        v
Chọn filter cuối cùng
        |
        v
readObject() / readUnshared()
        |
        v
ObjectInputFilter.checkInput(...)
        |
        +---- ALLOWED / tiếp tục
        +---- UNDECIDED / filter khác hoặc quy tắc mặc định quyết định
        +---- REJECTED / dừng deserialization
~~~

Factory cũng có thể dùng thông tin ngoài hai tham số, chẳng hạn `ThreadLocal`, call stack, module hoặc class loader. Đây là cơ sở để chọn filter theo ngữ cảnh.

### 4.1. Factory không phải filter

Hai thành phần có vai trò riêng:

- **Factory** chọn hoặc kết hợp filter khi stream được tạo/cấu hình.
- **Filter** kiểm tra class và số liệu tài nguyên trong khi stream đang được đọc.

Không nên đặt logic kiểm tra từng object vào factory. Logic đó thuộc `ObjectInputFilter.checkInput(FilterInfo)`.

## 5. Cấu hình factory trong Java 17

Java 17 cung cấp:

~~~java
ObjectInputFilter.Config.getSerialFilterFactory();
ObjectInputFilter.Config.setSerialFilterFactory(factory);
~~~

`getSerialFilterFactory()` luôn trả về factory đang hoạt động; nếu chưa đăng ký factory riêng, nó trả factory tích hợp sẵn.

`setSerialFilterFactory(...)` có các quy tắc vòng đời quan trọng:

- Factory chỉ được cấu hình đúng một lần.
- Phải cấu hình trước khi bất kỳ `ObjectInputStream` nào được tạo.
- Nếu factory đã được cấu hình qua system property hoặc Security property thì không thể thay bằng lời gọi API này.
- Nếu một `ObjectInputStream` đã được tạo trước đó, lời gọi cài factory có thể ném `IllegalStateException`.
- Tham số factory không được `null`.
- Nếu `current` khác `null`, factory phải trả filter khác `null`, để không vô tình vô hiệu hóa filter đã bật.

Vì vậy, hãy đăng ký factory ở giai đoạn bootstrap của ứng dụng, trước khi framework hoặc thư viện tạo `ObjectInputStream`.

### 5.1. Đăng ký trực tiếp bằng API

~~~java
import java.io.ObjectInputFilter;

ContextFilterFactory factory = new ContextFilterFactory();
ObjectInputFilter.Config.setSerialFilterFactory(factory);
~~~

Không gọi đoạn này nhiều lần trong cùng JVM. Nếu cần kiểm thử nhiều factory độc lập, hãy chạy các test cấu hình toàn JVM trong các process JVM riêng hoặc thiết kế test dùng chung một factory đã đăng ký.

### 5.2. Cấu hình bằng system property

Có thể cấu hình factory từ command line:

~~~bash
java -Djdk.serialFilterFactory=com.example.security.ContextFilterFactory \
     -jar application.jar
~~~

Giá trị là tên đầy đủ của class factory. Class phải:

- Là `public`.
- Có constructor không tham số `public`.
- Implement `BinaryOperator<ObjectInputFilter>`.
- Có thể được tải bởi application class loader.

Có thể đặt cùng cấu hình trong Security property `jdk.serialFilterFactory` của JDK.

System property có ưu tiên so với Security property cùng tên. Nếu factory được cấu hình qua property trong lúc khởi tạo `ObjectInputFilter.Config`, ứng dụng không thể thay nó bằng `setSerialFilterFactory`.

Đừng gọi `System.setProperty("jdk.serialFilterFactory", "...")` sau khi ứng dụng đã khởi tạo `ObjectInputFilter.Config` rồi mong factory được thay đổi. Hãy cấu hình property ở command line hoặc Security file trước khi JVM khởi chạy ứng dụng.

## 6. Kết hợp filter bằng ObjectInputFilter.merge

Java 17 cung cấp các phương thức hữu ích để tạo composite filter:

- `ObjectInputFilter.merge(filter, anotherFilter)`
- `ObjectInputFilter.rejectUndecidedClass(filter)`
- `ObjectInputFilter.allowFilter(predicate, otherStatus)`
- `ObjectInputFilter.rejectFilter(predicate, otherStatus)`

`merge` kết hợp kết quả của hai filter theo quy tắc:

1. Nếu một filter trả `REJECTED`, kết quả là `REJECTED`.
2. Nếu không filter nào từ chối và ít nhất một filter trả `ALLOWED`, kết quả là `ALLOWED`.
3. Nếu cả hai đều `UNDECIDED`, kết quả là `UNDECIDED`.

Điều này có nghĩa `merge` cho phép một quyết định `ALLOWED` thắng `UNDECIDED`, còn `REJECTED` luôn có quyền từ chối.

### 6.1. Merge không tự biến mọi filter thành giao của allow-list

Giả sử:

- Filter A trả `ALLOWED` cho lớp `com.example.dto.Message`.
- Filter B trả `UNDECIDED` cho lớp đó.

Kết quả merge là `ALLOWED`. Vì vậy, nếu bạn muốn một allow-list nghiêm ngặt, mỗi filter cần từ chối rõ ràng các lớp không nằm trong danh sách, ví dụ pattern kết thúc bằng `!*`.

`rejectUndecidedClass` có thể chuyển `UNDECIDED` thành `REJECTED` đối với class chưa được quyết định, nhưng không thể đảo ngược kết quả `ALLOWED` đã được `merge` tạo ra. Vì vậy, vẫn phải thiết kế semantics của từng filter cẩn thận.

### 6.2. Ví dụ filter theo allow-list

~~~java
ObjectInputFilter messageFilter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=12;maxrefs=200;maxbytes=500000;"
                + "maxarray=10000;com.example.dto.Message;!*");
~~~

Filter trên chỉ cho phép class `com.example.dto.Message` cùng các giới hạn tài nguyên đã đặt. Khi đồ thị object có thêm kiểu khác, cần liệt kê các kiểu đó theo đúng nhu cầu của giao thức.

Đối với ứng dụng có nhiều DTO, hãy liệt kê tập class thật sự cần thiết. Tránh dùng wildcard quá rộng như toàn bộ package ứng dụng nếu trong package đó còn nhiều kiểu không liên quan.

## 7. Chọn filter theo ThreadLocal context

Một cách triển khai được Java hỗ trợ là lưu filter theo ngữ cảnh trong `ThreadLocal`. Trước khi tạo `ObjectInputStream`, code đặt filter tương ứng vào thread hiện tại. Factory đọc giá trị đó và kết hợp với filter toàn JVM.

Mẫu dưới đây minh họa một factory theo allow-list:

~~~java
import java.io.ObjectInputFilter;
import java.util.Objects;
import java.util.function.BinaryOperator;
import java.util.function.Supplier;

public final class ContextFilterFactory
        implements BinaryOperator<ObjectInputFilter> {

    private final ThreadLocal<ObjectInputFilter> contextFilter =
            new ThreadLocal<>();

    @Override
    public ObjectInputFilter apply(
            ObjectInputFilter current,
            ObjectInputFilter requested) {

        if (current == null) {
            // Được gọi từ constructor ObjectInputStream.
            ObjectInputFilter context = contextFilter.get();
            ObjectInputFilter selected =
                    merge(requested, context);
            return context == null ? selected : strictAllowList(selected);
        }

        // Được gọi khi stream yêu cầu filter riêng.
        if (requested == null) {
            return current;
        }

        return merge(requested, current);
    }

    private static ObjectInputFilter merge(
            ObjectInputFilter first,
            ObjectInputFilter second) {
        if (first == null) {
            return second;
        }
        if (second == null) {
            return first;
        }
        return ObjectInputFilter.merge(first, second);
    }

    private static ObjectInputFilter strictAllowList(
            ObjectInputFilter filter) {
        if (filter == null) {
            return null;
        }
        return ObjectInputFilter.rejectUndecidedClass(filter);
    }

    public <T> T withContextFilter(
            ObjectInputFilter filter,
            Supplier<T> action) {
        Objects.requireNonNull(action, "action");

        ObjectInputFilter previous = contextFilter.get();
        try {
            if (filter == null) {
                contextFilter.remove();
            } else {
                contextFilter.set(filter);
            }
            return action.get();
        } finally {
            if (previous == null) {
                contextFilter.remove();
            } else {
                contextFilter.set(previous);
            }
        }
    }
}
~~~

Factory này:

1. Khi `current == null`, lấy filter được yêu cầu (thường là static JVM-wide filter) và filter của thread hiện tại.
2. Kết hợp hai filter nếu cả hai tồn tại.
3. Khi stream yêu cầu filter riêng, kết hợp filter đó với filter hiện tại của stream.
4. Giữ filter hiện tại nếu lời gọi mới không yêu cầu filter khác.
5. Không trả `null` khi `current` đã có filter.
6. Khôi phục giá trị `ThreadLocal` trước đó trong `finally`, tránh rò rỉ ngữ cảnh sang request tiếp theo trên thread pool.

Ví dụ dùng:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ObjectInputStream;
import java.io.ObjectInputFilter;

ContextFilterFactory factory = new ContextFilterFactory();
ObjectInputFilter messageFilter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=12;maxrefs=200;maxbytes=500000;"
                + "maxarray=10000;com.example.dto.Message;!*");

ObjectInputFilter.Config.setSerialFilterFactory(factory);

Object result = factory.withContextFilter(messageFilter, () -> {
    try (ObjectInputStream input = new ObjectInputStream(
            new ByteArrayInputStream(serializedBytes))) {
        return input.readObject();
    } catch (Exception e) {
        throw new IllegalStateException("Cannot read message", e);
    }
});
~~~

Trong ví dụ, filter theo ngữ cảnh được đặt trước khi tạo stream. Constructor gọi factory và factory gắn filter đã kết hợp vào stream. Khối `try-with-resources` đóng `ObjectInputStream` sau khi đọc.

Ví dụ minh họa cấu trúc; trong ứng dụng thật, hãy định nghĩa chính sách exception và kiểu kết quả cụ thể thay vì chuyển mọi lỗi thành `IllegalStateException`.

### 7.1. Vì sao phải khôi phục ThreadLocal trong finally?

Ứng dụng server thường tái sử dụng thread thông qua executor hoặc thread pool. Nếu đặt filter vào `ThreadLocal` nhưng không xóa/khôi phục sau khi xử lý, request tiếp theo có thể thừa hưởng chính sách của request trước.

Mẫu:

~~~java
ObjectInputFilter previous = context.get();
try {
    context.set(requestFilter);
    deserialize();
} finally {
    if (previous == null) {
        context.remove();
    } else {
        context.set(previous);
    }
}
~~~

Việc khôi phục giá trị trước đó còn hỗ trợ ngữ cảnh lồng nhau: một tác vụ có thể tạm thay filter rồi trả về filter của tác vụ cha.

### 7.2. ThreadLocal không tự truyền qua executor

`ThreadLocal` gắn với thread hiện tại. Nếu một request đặt filter ở thread A rồi giao việc deserialization sang thread B, thread B không tự nhận giá trị đó.

Vì vậy:

- Đặt context trên chính thread tạo `ObjectInputStream`.
- Nếu xử lý bất đồng bộ, truyền ngữ cảnh một cách tường minh tới task chạy trên thread đích.
- Không giả định thread pool hoặc `CompletableFuture` tự truyền `ThreadLocal`.
- Không dùng một biến mutable chung cho mọi request nếu các request có chính sách khác nhau.

## 8. Chọn ngữ cảnh bằng call stack, module hoặc class loader

ThreadLocal là một lựa chọn, không phải cách duy nhất. Factory có thể chọn filter theo:

- **Call stack:** xác định thành phần nào gọi code deserialization.
- **Module:** chọn chính sách dựa trên module của thư viện hoặc caller.
- **Class loader:** phân biệt plugin hoặc môi trường tải class khác nhau.
- **Library/context:** phân biệt các thành phần có hợp đồng dữ liệu khác nhau.
- **Thread context:** dùng thông tin do ứng dụng gắn vào thread hiện tại.

Ví dụ ý tưởng:

~~~java
Class<?> caller = StackWalker.getInstance(
        StackWalker.Option.RETAIN_CLASS_REFERENCE)
        .getCallerClass();

Module callerModule = caller.getModule();
String moduleName = callerModule.getName();
~~~

Sau đó factory có thể ánh xạ `moduleName` hoặc thông tin caller sang một filter đã định nghĩa. Đây là ví dụ khái niệm; khi triển khai cần xác định chính xác caller mà factory nhìn thấy trong call stack, vì stack có thể chứa các lớp trung gian của framework.

Không nên dùng call stack hoặc class loader như bằng chứng xác thực danh tính người dùng. Chúng chỉ là thông tin ngữ cảnh kỹ thuật để chọn chính sách deserialization.

## 9. Factory và filter toàn JVM: chính sách phải kết hợp có chủ đích

Một factory tùy chỉnh có thể kết hợp ba nguồn:

1. Static JVM-wide filter: quy tắc chung của tiến trình.
2. Context filter: allow-list và giới hạn cho thành phần hiện tại.
3. Stream-specific filter: điều kiện bổ sung do caller của stream yêu cầu.

Sơ đồ:

~~~text
                  Static JVM-wide filter
                            |
                            v
Context filter ----> Filter factory <---- Stream-specific filter
                            |
                            v
                 Composite ObjectInputFilter
                            |
                            v
                     ObjectInputStream
                            |
                            v
                   readObject / readUnshared
~~~

Khi kết hợp:

- `REJECTED` từ bất kỳ filter nào phải được giữ lại để chặn dữ liệu.
- Nếu cần allow-list nghiêm ngặt, mọi lớp không được phép phải nhận `REJECTED`.
- `UNDECIDED` không nên bị hiểu nhầm là đã được cho phép rõ ràng.
- Không để filter riêng của stream vô tình loại bỏ chính sách toàn JVM.

### 9.1. Factory mặc định và factory tùy chỉnh

| Hành vi | Factory mặc định | Factory tùy chỉnh |
| --- | --- | --- |
| Tạo stream | Gắn static JVM-wide filter nếu có | Có thể chọn filter theo context và kết hợp global filter |
| Đặt stream filter | Filter được yêu cầu thay filter ban đầu theo hành vi mặc định | Có thể kết hợp filter yêu cầu với filter hiện tại |
| Chính sách theo thread/module/caller | Không tự chọn filter riêng theo các context đó | Ứng dụng tự triển khai |
| Kiểm soát cách merge | Theo hành vi tương thích tích hợp sẵn | Do factory quyết định |

Chỉ cần static filter toàn JVM cho ứng dụng đơn giản với một chính sách chung. Dùng custom factory khi thật sự có nhiều ngữ cảnh deserialization cần các filter khác nhau hoặc cần bảo đảm filter stream không ghi đè filter nền.

## 10. Cấu hình stream-specific filter

Sau khi tạo `ObjectInputStream`, có thể đặt filter riêng:

~~~java
try (ObjectInputStream input =
        new ObjectInputStream(source)) {

    input.setObjectInputFilter(streamFilter);
    Object value = input.readObject();
}
~~~

Trong Java 17, `setObjectInputFilter`:

- Chỉ được gọi một lần trên mỗi stream.
- Phải gọi trước khi đọc object bằng `readObject()` hoặc `readUnshared()`.
- Đi qua JVM-wide filter factory để chọn filter cuối cùng.
- Không được thay filter khác `null` bằng filter kết quả `null`.

Nếu factory cần kết hợp filter riêng với filter ban đầu, hãy làm điều đó trong `apply(current, requested)`. Không gọi `setObjectInputFilter` nhiều lần để cố cập nhật chính sách sau khi đã đọc dữ liệu.

## 11. Cấu hình factory qua property

Nếu muốn cài factory trước khi ứng dụng bắt đầu chạy, có thể dùng:

~~~bash
java -Djdk.serialFilterFactory=com.example.security.ContextFilterFactory \
     -Djdk.serialFilter="maxdepth=20;maxrefs=1000;maxbytes=2000000" \
     -jar application.jar
~~~

Hai property có vai trò khác nhau:

| Property | Chức năng |
| --- | --- |
| `jdk.serialFilter` | Cấu hình static JVM-wide filter |
| `jdk.serialFilterFactory` | Chỉ định class triển khai factory cho toàn JVM |

System property có ưu tiên so với Security property cùng tên. Nếu factory được cấu hình qua property trong lúc khởi tạo `ObjectInputFilter.Config`, ứng dụng không thể thay nó bằng `setSerialFilterFactory`.

Đừng gọi `System.setProperty("jdk.serialFilterFactory", "...")` sau khi ứng dụng đã khởi tạo `ObjectInputFilter.Config` rồi mong factory được thay đổi. Hãy cấu hình property ở command line hoặc Security file trước khi JVM khởi chạy ứng dụng.

## 12. Kiểm tra và quan sát filter đang hoạt động

Có thể lấy factory và filter toàn JVM:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter globalFilter =
        ObjectInputFilter.Config.getSerialFilter();

var factory =
        ObjectInputFilter.Config.getSerialFilterFactory();

System.out.println("Global filter: " + globalFilter);
System.out.println("Factory: " + factory);
~~~

`getSerialFilter()` trả `null` nếu static filter chưa được cấu hình. `getSerialFilterFactory()` trả factory đang hoạt động; nếu chưa đặt custom factory, nó trả factory tích hợp sẵn.

Sau khi tạo stream, có thể xem filter đã được factory chọn:

~~~java
ObjectInputFilter active = input.getObjectInputFilter();
System.out.println("Stream filter: " + active);
~~~

Đây là cách kiểm tra cấu hình trong môi trường chạy. Không log dữ liệu object nhạy cảm chỉ để chẩn đoán filter.

### 12.1. Logging filter actions

JDK hỗ trợ logging cho serialization filter để quan sát quyết định. Cấu hình logging có thể giúp phát hiện:

- Class nào được kiểm tra.
- Class nào bị từ chối.
- Giới hạn độ sâu, số tham chiếu hoặc số byte nào bị vượt.
- Một thành phần có đang gửi các kiểu object ngoài hợp đồng hay không.

Hãy bật logging theo nhu cầu điều tra và quản lý lượng log. Không nên mặc định ghi toàn bộ dữ liệu nhạy cảm hoặc để log quá chi tiết trong production lâu dài.

## 13. Lỗi thường gặp khi triển khai filter factory

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `setSerialFilterFactory` ném `IllegalStateException` | Đã tạo `ObjectInputStream` hoặc factory đã được cấu hình | Đăng ký factory sớm trong bootstrap và chỉ đăng ký một lần |
| Filter stream làm mất filter toàn JVM | Factory mặc định thay filter ban đầu bằng stream filter | Dùng factory tùy chỉnh để kết hợp hai chính sách nếu cần |
| Lớp ngoài allow-list vẫn được đọc | Filter trả `UNDECIDED` cho lớp không khớp | Dùng `!*`, filter từ chối rõ ràng hoặc `rejectUndecidedClass` phù hợp |
| Một filter cho phép lớp mà filter khác chưa quyết định | `merge` trả `ALLOWED` nếu một bên allow và bên kia undecided | Thiết kế từng filter với semantics rõ; strict allow-list phải từ chối lớp ngoài danh sách |
| Factory trả `null` khi `current` đã khác null | Vô tình loại bỏ filter hiện tại | Luôn giữ filter hiện tại hoặc trả composite không null |
| Request tiếp theo thừa hưởng filter trước | Không xóa/khôi phục `ThreadLocal` | Khôi phục trong `finally` |
| Async task dùng sai context | `ThreadLocal` không tự truyền sang thread khác | Truyền context rõ ràng và đặt trên thread tạo stream |
| Test chạy riêng thành công nhưng suite thất bại | Factory là cấu hình JVM-wide, chỉ đặt một lần | Dùng một factory chung hoặc chạy test cấu hình trong JVM riêng |
| Filter có giới hạn class nhưng vẫn đọc object quá lớn | Chưa giới hạn graph depth, references, bytes hoặc arrays | Đặt giới hạn tài nguyên cùng allow-list |
| Nghĩ factory bảo vệ mọi parser | Factory chỉ áp dụng cho `ObjectInputStream` Java Serialization | Dùng cơ chế kiểm tra riêng cho JSON, XML, YAML hoặc định dạng khác |

## 14. Những giới hạn và nguyên tắc bảo mật

Filter factory là một lớp phòng vệ quan trọng, nhưng không biến Java Serialization thành định dạng an toàn cho mọi dữ liệu đầu vào.

- Tránh deserialization dữ liệu không đáng tin cậy khi có thể dùng định dạng dữ liệu đơn giản hơn.
- Xây dựng allow-list theo từng use case; không cho phép toàn bộ package hoặc module chỉ vì thuận tiện.
- Đặt giới hạn `maxdepth`, `maxrefs`, `maxbytes`, `maxarray` theo đặc tính dữ liệu hợp lệ.
- Xem xét cả class trong object graph, mảng, tham chiếu và các kiểu hỗ trợ.
- Không coi filter là thay thế cho xác thực dữ liệu sau khi đọc.
- Không dùng `UNDECIDED` như một cách cho phép ngầm khi xây dựng allow-list.
- Giữ factory an toàn khi nhiều thread gọi đồng thời.
- Không lưu trạng thái request trong biến instance mutable dùng chung; dùng context có phạm vi và vòng đời rõ ràng.
- Chỉ mở rộng quyền deserialization khi có hợp đồng dữ liệu và lý do cụ thể.

Filter được áp dụng trong quá trình đọc object; nó không thay thế xác thực kết nối, xác thực người gửi, kiểm tra tính toàn vẹn hoặc kiểm tra quy tắc nghiệp vụ của dữ liệu.

## 15. Khi nào nên dùng filter factory?

| Tình huống | Cách tiếp cận |
| --- | --- |
| Ứng dụng nhỏ, mọi stream dùng cùng chính sách | Static JVM-wide filter có thể đủ |
| Mỗi stream có allow-list riêng, không cần context phức tạp | Đặt stream-specific filter và hiểu hành vi factory mặc định |
| Nhiều thư viện hoặc module cần tập class khác nhau | Dùng custom filter factory để chọn theo context |
| Cần giữ filter toàn JVM đồng thời áp dụng filter stream | Factory tùy chỉnh để kết hợp filter hiện tại và filter yêu cầu |
| Deserialization chạy trong nhiều request trên thread pool | Có thể dùng ThreadLocal context, phải khôi phục trong `finally` |
| Cần chọn policy theo module hoặc caller | Factory có thể xem module/call stack, nhưng phải thiết kế kiểm tra context rõ ràng |

Không cần custom factory chỉ vì Java 17 có API này. Hãy dùng nó khi chính sách theo ngữ cảnh mang lại giá trị rõ ràng và có thể được kiểm thử.

## 16. Câu hỏi tự kiểm tra

**1. Filter factory theo ngữ cảnh được bổ sung trong Java phiên bản nào?**  
Java 17, theo JEP 415.

**2. Filter factory có kiểu chức năng nào?**  
`BinaryOperator<ObjectInputFilter>`, nhận filter hiện tại và filter được yêu cầu rồi trả filter cuối cùng cho stream.

**3. Factory được gọi vào những thời điểm nào?**  
Khi tạo `ObjectInputStream` và khi gọi `setObjectInputFilter` trên stream.

**4. Khi constructor `ObjectInputStream` gọi factory, hai tham số là gì?**  
`current` là `null`; `requested` là static JVM-wide filter.

**5. Khi gọi `setObjectInputFilter`, hai tham số là gì?**  
`current` là filter đang gắn với stream; `requested` là filter được truyền vào phương thức.

**6. Factory mặc định xử lý filter riêng của stream ra sao?**  
Filter riêng được yêu cầu thay filter ban đầu theo hành vi tích hợp sẵn, thay vì tự động merge với filter toàn JVM.

**7. Vì sao custom factory cần giữ filter hiện tại nếu nó khác `null`?**  
Để không vô tình tắt filtering đã được bật; factory phải trả filter khác `null` trong trường hợp này.

**8. `ObjectInputFilter.merge` xử lý trạng thái thế nào?**  
`REJECTED` thắng; nếu không có từ chối thì `ALLOWED` từ một trong hai filter thắng; nếu cả hai `UNDECIDED`, kết quả là `UNDECIDED`.

**9. Vì sao allow-list nên có `!*` ở cuối?**  
Để lớp không khớp pattern bị từ chối rõ ràng, thay vì nhận `UNDECIDED`.

**10. `ThreadLocal` giúp gì cho factory?**  
Lưu filter theo ngữ cảnh của thread đang tạo stream để factory chọn chính sách phù hợp.

**11. Vì sao cần khôi phục hoặc xóa ThreadLocal trong `finally`?**  
Để thread pool không mang filter của request trước sang request sau.

**12. Có thể gọi `setSerialFilterFactory` sau khi tạo một `ObjectInputStream` không?**  
Không. Factory phải được cấu hình trước khi bất kỳ `ObjectInputStream` nào được tạo và chỉ cấu hình một lần.

**13. `System.setProperty("jdk.serialFilterFactory", ...)` sau khi JVM chạy có đủ không?**  
Không. Cần cấu hình property lúc khởi chạy/qua Security property hoặc gọi API đúng thời điểm.

**14. Filter factory có kiểm tra từng object trực tiếp không?**  
Không. Factory chọn filter; filter được gắn vào stream mới kiểm tra class, mảng và số liệu đồ thị trong quá trình đọc.

**15. Filter factory có bảo vệ mọi bộ giải mã JSON hoặc XML không?**  
Không. Nó áp dụng cho Java Serialization thông qua `ObjectInputStream`.

## Tài liệu tham khảo chính thức

- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): mục tiêu và cơ chế chọn filter theo ngữ cảnh trong Java 17.
- [Java SE 17 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): `FilterInfo`, `Status`, `merge`, `rejectUndecidedClass` và mô hình factory.
- [Java SE 17 API — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): `getSerialFilterFactory`, `setSerialFilterFactory`, `getSerialFilter`, `setSerialFilter` và `createFilter`.
- [Java SE 17 API — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): thời điểm factory được gọi và quy tắc `setObjectInputFilter`.
- [Java SE 17 — Serialization Filtering Guide](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html): filter toàn JVM, filter riêng cho stream, allow-list, reject-list và filter factory.

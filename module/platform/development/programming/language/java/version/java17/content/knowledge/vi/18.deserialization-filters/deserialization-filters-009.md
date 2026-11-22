# Kết hợp chính sách bằng ObjectInputFilter.merge trong Java 17

**Chủ đề:** Java 17 → Lọc giải tuần tự hóa  
**Trọng tâm:** Kết hợp nhiều chính sách lọc deserialization bằng `ObjectInputFilter.merge`; hiểu thứ tự ưu tiên của `REJECTED`, `ALLOWED`, `UNDECIDED`, cách xử lý filter null, và cách ghép allowlist với giới hạn tài nguyên để bảo vệ `ObjectInputStream`.

Java 17 cung cấp `ObjectInputFilter.merge` để kết hợp hai filter thành một filter tổng hợp. API này được bổ sung trong Java 17 cùng các tiện ích `allowFilter`, `rejectFilter` và `rejectUndecidedClass`. Nó hữu ích khi mỗi thành phần chịu trách nhiệm cho một phần chính sách: filter thứ nhất kiểm tra loại lớp, filter thứ hai giới hạn độ sâu hoặc kích thước object graph, còn filter khác có thể áp dụng quy tắc riêng cho một ngữ cảnh xử lý.

Điểm cần nhớ nhất là quy tắc kết hợp của `merge`:

- Nếu **một trong hai filter trả `REJECTED`**, kết quả là `REJECTED`.
- Nếu không filter nào từ chối và **ít nhất một filter trả `ALLOWED`**, kết quả là `ALLOWED`.
- Nếu cả hai đều trả `UNDECIDED`, kết quả là `UNDECIDED`.

Do đó, `merge` không phải phép AND yêu cầu cả hai filter đều phải trả `ALLOWED`. Nó dùng nguyên tắc **từ chối có quyền phủ quyết; một quyết định cho phép đủ để tạo kết quả cho phép nếu không có filter nào từ chối**. Cách thiết kế trạng thái của từng filter quyết định chính sách cuối cùng.

## 1. ObjectInputFilter dùng trong giai đoạn nào?

Java Serialization có thể tái tạo một object graph từ byte stream. Nếu dữ liệu đến từ nguồn không đáng tin cậy, các lớp được giải tuần tự hóa và cấu trúc object graph có thể gây rủi ro: tạo object ngoài dự kiến, tiêu tốn bộ nhớ, tạo đồ thị quá sâu hoặc chứa mảng quá lớn.

`ObjectInputFilter` cho phép kiểm tra thông tin của object graph trong lúc `ObjectInputStream` đọc dữ liệu. Filter có thể đánh giá:

- Lớp của đối tượng sắp được giải tuần tự hóa.
- Độ dài mảng.
- Độ sâu hiện tại của object graph.
- Số lượng object reference đã được đọc.
- Số byte đã tiêu thụ từ stream.

Filter được gọi trong quá trình stream giải tuần tự hóa object graph. Nó có thể trả về một trong ba trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `ALLOWED` | Filter chấp nhận thông tin đang kiểm tra. |
| `REJECTED` | Filter từ chối; `ObjectInputStream` dừng việc giải tuần tự hóa đối tượng đó và thường ném `InvalidClassException`. |
| `UNDECIDED` | Filter không đưa ra quyết định cho thông tin này. |

**`UNDECIDED` không đồng nghĩa với từ chối.** Nếu filter đang hoạt động trả về `UNDECIDED`, deserialization có thể tiếp tục như không có quyết định từ filter đó. Muốn một allowlist chặt chẽ, cần bảo đảm lớp không nằm trong danh sách không bị để ở trạng thái `UNDECIDED` một cách vô tình.

Filter không được gọi cho giá trị primitive và các instance `java.lang.String` được mã hóa trực tiếp trong serialization stream. Với array, filter nhận lớp array cùng độ dài; với object reference đã được đọc trước đó, `serialClass()` có thể là `null` và filter vẫn có thể kiểm tra các metrics.

## 2. Cú pháp và hợp đồng của ObjectInputFilter.merge

Cú pháp:

~~~java
ObjectInputFilter combined =
    ObjectInputFilter.merge(filter, anotherFilter);
~~~

Phương thức có từ Java 17:

~~~java
static ObjectInputFilter merge(
    ObjectInputFilter filter,
    ObjectInputFilter anotherFilter
)
~~~

Hợp đồng:

1. `filter` (đối số thứ nhất) phải khác `null`.
2. Nếu `anotherFilter` (đối số thứ hai) là `null`, phương thức trả lại `filter`.
3. Nếu cả hai filter khác `null`, phương thức trả về một filter tổng hợp gọi các filter theo thứ tự và kết hợp trạng thái.
4. Filter thứ nhất được gọi trước. Nếu nó trả `REJECTED`, filter thứ hai không cần được gọi.
5. Nếu filter thứ nhất không từ chối, filter thứ hai được gọi. Chỉ cần một filter trả `REJECTED`, kết quả cuối là `REJECTED`.

Các trường hợp null:

| Lời gọi | Kết quả |
| --- | --- |
| `ObjectInputFilter.merge(filterA, filterB)` | Tạo filter kết hợp. |
| `ObjectInputFilter.merge(filterA, null)` | Trả lại `filterA`. |
| `ObjectInputFilter.merge(null, filterB)` | Ném `NullPointerException`. |
| `ObjectInputFilter.merge(null, null)` | Ném `NullPointerException`. |

Vì đối số thứ nhất bắt buộc khác null, nếu ứng dụng có hai filter tùy chọn thì phải xử lý trường hợp filter đầu tiên null trước khi gọi `merge`.

## 3. Bảng kết hợp ba trạng thái

Đây là bảng kết quả khi cả hai filter đều tồn tại:

| Filter thứ nhất | Filter thứ hai | Kết quả của merge |
| --- | --- | --- |
| `REJECTED` | `REJECTED` | `REJECTED` |
| `REJECTED` | `ALLOWED` | `REJECTED` |
| `REJECTED` | `UNDECIDED` | `REJECTED` |
| `ALLOWED` | `REJECTED` | `REJECTED` |
| `ALLOWED` | `ALLOWED` | `ALLOWED` |
| `ALLOWED` | `UNDECIDED` | `ALLOWED` |
| `UNDECIDED` | `REJECTED` | `REJECTED` |
| `UNDECIDED` | `ALLOWED` | `ALLOWED` |
| `UNDECIDED` | `UNDECIDED` | `UNDECIDED` |

Có thể ghi nhớ bằng thứ tự ưu tiên:

~~~text
               Có filter nào REJECTED?
                    /        \
                  Có          Không
                  |             |
               REJECTED    Có filter nào ALLOWED?
                              /       \
                            Có         Không
                            |            |
                         ALLOWED     UNDECIDED
~~~

### 3.1. Vì sao không phải phép AND?

Giả sử:

- Filter A cho phép lớp `Invoice`.
- Filter B kiểm tra giới hạn tài nguyên và trả `UNDECIDED` nếu giới hạn chưa bị vượt.

Khi kiểm tra `Invoice`, A trả `ALLOWED`, B trả `UNDECIDED`; kết quả `merge` là `ALLOWED`. Đây là điều mong muốn: lớp được allowlist chấp nhận và giới hạn tài nguyên không phát hiện vi phạm.

Nếu giới hạn bị vượt, B trả `REJECTED`; dù A trả `ALLOWED`, kết quả vẫn là `REJECTED`. Vì vậy filter giới hạn có quyền phủ quyết.

Nếu cả hai filter đều phải trả `ALLOWED` mới được chấp nhận, `merge` mặc định không diễn đạt chính sách AND đó. Cần viết composite filter riêng và xử lý `UNDECIDED` phù hợp, hoặc thiết kế từng filter để trạng thái của chúng thể hiện đúng chính sách.

## 4. Thiết kế filter chuyên trách

Một cách tổ chức dễ bảo trì là chia chính sách thành các filter nhỏ:

| Filter | Trách nhiệm | Khi không có vấn đề |
| --- | --- | --- |
| Allowlist | Chỉ cho phép các lớp đã xác định. | Trả `ALLOWED` cho lớp được phép; trả `REJECTED` cho lớp ngoài danh sách. |
| Blocklist | Từ chối lớp nguy hiểm hoặc không được phép. | Trả `UNDECIDED` cho lớp không khớp quy tắc từ chối. |
| Resource limits | Giới hạn depth, references, bytes và array length. | Trả `UNDECIDED` khi mọi giới hạn đều trong ngưỡng. |
| Context policy | Quy định lớp nào được phép trong một luồng nghiệp vụ hoặc module cụ thể. | Trả trạng thái theo phạm vi trách nhiệm của ngữ cảnh. |

Filter chỉ nên đưa ra quyết định trong phạm vi nó hiểu. Ví dụ, filter giới hạn tài nguyên không cần trả `ALLOWED` cho mọi lớp hợp lệ về kích thước; nó chỉ cần trả `REJECTED` khi vượt ngưỡng và `UNDECIDED` khi không có vi phạm. Khi ghép với allowlist, cách này tránh việc filter giới hạn vô tình cấp quyền cho lớp ngoài danh sách.

## 5. Kết hợp allowlist với giới hạn tài nguyên

Đây là mẫu thường gặp: chỉ chấp nhận những kiểu dữ liệu ứng dụng dự kiến, đồng thời giới hạn kích thước object graph.

### 5.1. Tạo allowlist bằng allowFilter

Java 17 cung cấp:

~~~java
ObjectInputFilter.allowFilter(
    Predicate<Class<?>> predicate,
    ObjectInputFilter.Status otherStatus
)
~~~

Filter trả:

- `UNDECIDED` nếu `FilterInfo.serialClass()` là `null`.
- `ALLOWED` nếu predicate trả `true`.
- `otherStatus` nếu predicate trả `false`.

Để tạo allowlist chặt, truyền `Status.REJECTED` làm `otherStatus`:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter allowedClasses = ObjectInputFilter.allowFilter(
    type -> type == Message.class || type == Notice.class,
    ObjectInputFilter.Status.REJECTED
);
~~~

Như vậy, lớp được liệt kê trả `ALLOWED`; mọi lớp khác có `serialClass` khác null trả `REJECTED`. Những lần filter chỉ nhận metrics với `serialClass == null` vẫn trả `UNDECIDED`.

### 5.2. Tạo filter giới hạn tài nguyên

`FilterInfo` cung cấp các metrics để phát hiện object graph quá lớn:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter resourceLimits = info -> {
    if (info.depth() > 20
            || info.references() > 10_000
            || info.streamBytes() > 1_000_000
            || (info.arrayLength() >= 0 && info.arrayLength() > 100_000)) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
~~~

Ý nghĩa:

- `depth()`: độ sâu hiện tại của object graph.
- `references()`: số object reference đã được đọc.
- `streamBytes()`: số byte đã đọc từ stream.
- `arrayLength()`: độ dài mảng đang được kiểm tra; giá trị âm biểu thị lần kiểm tra hiện tại không phải một mảng.

Các con số trong ví dụ chỉ để minh họa. Ứng dụng phải chọn giới hạn dựa trên kích thước dữ liệu hợp lệ, cấu trúc object graph và tài nguyên cho phép. Không sao chép ngưỡng mẫu vào production mà chưa đánh giá.

### 5.3. Dùng merge để ghép hai filter

~~~java
ObjectInputFilter combined =
    ObjectInputFilter.merge(allowedClasses, resourceLimits);
~~~

Kết quả:

- Lớp nằm trong allowlist, tài nguyên chưa vượt giới hạn: `ALLOWED + UNDECIDED` → `ALLOWED`.
- Lớp nằm ngoài allowlist: `REJECTED` → `REJECTED`.
- Lớp được phép nhưng object graph vượt giới hạn: `ALLOWED + REJECTED` → `REJECTED`.
- Lần kiểm tra chỉ có metrics và chưa vượt ngưỡng: `UNDECIDED + UNDECIDED` → `UNDECIDED`.

Đây là cách kết hợp hai chính sách bổ sung cho nhau: allowlist quyết định lớp nào được phép, resource filter có quyền từ chối object graph quá lớn.

## 6. Ví dụ đầy đủ: deserialize với filter đã merge

Tạo tệp **`FilterMergeDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class FilterMergeDemo {
    static final class Message implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String text;
        private final int priority;

        Message(String text, int priority) {
            this.text = text;
            this.priority = priority;
        }

        @Override
        public String toString() {
            return "Message[text=" + text + ", priority=" + priority + "]";
        }
    }

    static final class UnexpectedPayload implements Serializable {
        private static final long serialVersionUID = 1L;
    }

    private static byte[] serialize(Object value) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(value);
        }
        return bytes.toByteArray();
    }

    private static Object deserialize(
            byte[] bytes,
            ObjectInputFilter filter
    ) throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            // Phải đặt filter trước lần đọc object đầu tiên.
            in.setObjectInputFilter(filter);
            return in.readObject();
        }
    }

    private static ObjectInputFilter createFilter() {
        ObjectInputFilter allowlist = ObjectInputFilter.allowFilter(
            type -> type == Message.class,
            ObjectInputFilter.Status.REJECTED
        );

        ObjectInputFilter limits = info -> {
            if (info.depth() > 10
                    || info.references() > 100
                    || info.streamBytes() > 100_000
                    || (info.arrayLength() >= 0
                        && info.arrayLength() > 10_000)) {
                return ObjectInputFilter.Status.REJECTED;
            }
            return ObjectInputFilter.Status.UNDECIDED;
        };

        return ObjectInputFilter.merge(allowlist, limits);
    }

    public static void main(String[] args) throws Exception {
        ObjectInputFilter filter = createFilter();

        byte[] acceptedBytes = serialize(new Message("Hello", 1));
        Object accepted = deserialize(acceptedBytes, filter);
        System.out.println(accepted);

        byte[] rejectedBytes = serialize(new UnexpectedPayload());
        try {
            deserialize(rejectedBytes, filter);
        } catch (InvalidClassException e) {
            System.out.println("Rejected: " + e.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~shell
javac --release 17 FilterMergeDemo.java
java FilterMergeDemo
~~~

Phần kết quả quan trọng:

~~~text
Message[text=Hello, priority=1]
Rejected: filter status: REJECTED
~~~

Thông báo lỗi có thể kèm thêm tên lớp hoặc chi tiết tùy JDK. Kết quả cần quan sát là `Message` được chấp nhận, còn `UnexpectedPayload` bị từ chối bởi allowlist. Nếu object graph của `Message` vượt giới hạn, filter tài nguyên cũng có thể từ chối nó.

Trong ứng dụng thực tế, lớp dữ liệu được phép có thể cần các kiểu component khác. Hãy liệt kê đúng các kiểu được phép theo object graph thực tế; đừng mở rộng allowlist thành toàn bộ package hoặc mọi lớp chỉ để tránh lỗi.

## 7. Kết hợp blocklist với resource filter

Không phải chính sách nào cũng dùng allowlist. Một hệ thống có thể cần từ chối rõ một số loại lớp nguy hiểm, còn các lớp khác được xử lý bởi filter khác.

Java 17 có `rejectFilter`:

~~~java
ObjectInputFilter.rejectFilter(
    Predicate<Class<?>> predicate,
    ObjectInputFilter.Status otherStatus
)
~~~

Ví dụ:

~~~java
ObjectInputFilter blockLegacyTypes = ObjectInputFilter.rejectFilter(
    type -> type.getName().startsWith("com.example.legacy."),
    ObjectInputFilter.Status.UNDECIDED
);
~~~

Filter này trả:

- `REJECTED` nếu tên lớp nằm trong package bị chặn.
- `UNDECIDED` nếu lớp không khớp.
- `UNDECIDED` nếu `serialClass()` là `null`.

Ghép với giới hạn tài nguyên:

~~~java
ObjectInputFilter policy =
    ObjectInputFilter.merge(blockLegacyTypes, resourceLimits);
~~~

Lớp thuộc package bị chặn sẽ bị từ chối. Lớp khác không bị blocklist kết luận; resource filter cũng chỉ từ chối khi phát hiện vượt ngưỡng. Nếu cả hai trả `UNDECIDED`, kết quả vẫn `UNDECIDED`.

**Cảnh báo:** đây là blocklist, không phải allowlist. Lớp không khớp package bị chặn không tự động được chứng minh là an toàn. Nếu dữ liệu đến từ nguồn không đáng tin cậy, thường cần một allowlist cụ thể cho từng ngữ cảnh thay vì chỉ chặn vài package.

## 8. rejectUndecidedClass: biến quyết định chưa rõ thành từ chối

Java 17 có:

~~~java
ObjectInputFilter.rejectUndecidedClass(filter)
~~~

Wrapper này gọi filter bên trong và chuyển kết quả `UNDECIDED` thành `REJECTED` đối với lớp, với xử lý đặc biệt cho array và primitive array theo hợp đồng API. Nếu `serialClass()` là `null`, trạng thái vẫn là `UNDECIDED` vì lần gọi đó chỉ chứa metrics của object graph.

Ví dụ:

~~~java
ObjectInputFilter strictPolicy =
    ObjectInputFilter.rejectUndecidedClass(
        ObjectInputFilter.merge(allowlist, resourceLimits)
    );
~~~

Với cách thiết kế trong ví dụ trước:

- Lớp được allowlist chấp nhận và không vượt giới hạn: kết quả `ALLOWED`, giữ nguyên.
- Lớp bị allowlist từ chối: kết quả `REJECTED`, giữ nguyên.
- Lớp chưa có filter nào quyết định: `UNDECIDED` được đổi thành `REJECTED`.
- Lần kiểm tra metrics-only: vẫn có thể là `UNDECIDED`.

Điều này tạo một chính sách fail-closed cho lớp: lớp nào không được cho phép rõ ràng sẽ bị từ chối.

### 8.1. Không bọc rejectUndecidedClass một cách máy móc

Nếu chỉ có blocklist và resource filter, cả hai có thể trả `UNDECIDED` cho một lớp hợp lệ chưa bị chặn. Bọc `rejectUndecidedClass` quanh composite đó sẽ từ chối luôn lớp ấy.

Vì vậy:

- Dùng `rejectUndecidedClass` khi chính sách có một nguồn allow rõ ràng.
- Không dùng nó như một bước trang trí mặc định cho mọi filter.
- Kiểm tra các lớp phụ thuộc, array component và lớp trong object graph trước khi áp dụng.

## 9. Kết hợp filter tạo từ pattern string

`ObjectInputFilter.Config.createFilter` tạo filter từ chuỗi pattern. Pattern có thể mô tả giới hạn tài nguyên và tên lớp/package được phép hoặc từ chối.

Ví dụ:

~~~java
ObjectInputFilter patternFilter =
    ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=10000;maxbytes=1000000;"
        + "com.example.dto.*;!*"
    );
~~~

Trong ví dụ:

- `maxdepth=20`: giới hạn độ sâu object graph.
- `maxrefs=10000`: giới hạn số reference.
- `maxbytes=1000000`: giới hạn byte đọc từ stream.
- `com.example.dto.*`: cho phép lớp trong package được chỉ định theo cú pháp pattern.
- `!*`: từ chối các lớp không khớp những pattern trước đó.

Có thể ghép filter pattern với filter riêng của ngữ cảnh:

~~~java
ObjectInputFilter contextFilter = ObjectInputFilter.allowFilter(
    type -> type == ImportRequest.class,
    ObjectInputFilter.Status.UNDECIDED
);

ObjectInputFilter combined =
    ObjectInputFilter.merge(patternFilter, contextFilter);
~~~

Hai filter đều có quyền từ chối. Vì vậy, một lớp phải không bị bất kỳ filter nào từ chối; chỉ cần một filter trả `ALLOWED` cũng chưa đủ nếu filter kia trả `REJECTED`.

Trong ví dụ này, `contextFilter` chỉ đưa ra quyết định cho `ImportRequest` và trả `UNDECIDED` với lớp khác. Nếu dùng `REJECTED` làm trạng thái còn lại, filter ngữ cảnh sẽ từ chối tất cả DTO khác mà pattern filter có thể cho phép.

Pattern string hữu ích khi chính sách có thể cấu hình qua system property hoặc file cấu hình. Lambda hữu ích khi điều kiện phụ thuộc vào logic Java, class loader, module hoặc metadata ứng dụng.

## 10. Dùng filter đã merge cho ObjectInputStream

Sau khi tạo filter tổng hợp, đặt nó lên stream trước khi đọc object:

~~~java
try (ObjectInputStream in =
        new ObjectInputStream(inputStream)) {
    in.setObjectInputFilter(combinedFilter);
    Object value = in.readObject();
}
~~~

Một số điểm cần chú ý:

- Đặt filter trước lần đọc object đầu tiên.
- `setObjectInputFilter` chỉ được gọi một lần cho mỗi stream.
- Filter được áp dụng trong quá trình stream giải tuần tự hóa object graph.
- Nếu filter trả `REJECTED`, việc đọc đối tượng bị dừng và phát sinh `InvalidClassException`.
- Filter stream-specific chỉ bảo vệ stream được gắn filter đó.
- Nếu ứng dụng tạo nhiều `ObjectInputStream`, cần bảo đảm mỗi stream có chính sách phù hợp.

Không nên gọi `setObjectInputFilter` sau khi stream đã bắt đầu đọc object để mong áp dụng ngược cho những object đã được xử lý.

## 11. Kết hợp chính sách qua filter factory trong Java 17

Trong ứng dụng có nhiều thư viện hoặc nhiều ngữ cảnh deserialization, một filter cố định cho toàn JVM có thể không đủ. Java 17 bổ sung cơ chế **deserialization filter factory** theo JEP 415.

Factory là một `BinaryOperator<ObjectInputFilter>`. Nó được gọi khi:

1. Một `ObjectInputStream` được tạo, với filter hiện tại là `null` và filter được yêu cầu là filter tĩnh toàn JVM (nếu có).
2. Ứng dụng gọi `ObjectInputStream.setObjectInputFilter`, với filter hiện tại và filter mới được yêu cầu.

Factory có thể dựa vào ngữ cảnh thực thi để chọn hoặc kết hợp chính sách. Ví dụ tối giản:

~~~java
import java.io.ObjectInputFilter;
import java.util.function.BinaryOperator;

BinaryOperator<ObjectInputFilter> factory = (current, requested) -> {
    if (current == null) {
        return requested;
    }
    if (requested == null) {
        return current;
    }
    return ObjectInputFilter.merge(requested, current);
};

ObjectInputFilter.Config.setSerialFilterFactory(factory);
~~~

Đây là ví dụ về cách ghép filter hiện tại và filter được yêu cầu. `setSerialFilterFactory` chỉ được cấu hình một lần và phải được gọi trước khi bất kỳ `ObjectInputStream` nào được tạo. Trong hệ thống thực tế, factory có thể cần lấy thêm filter theo thread, module, thư viện gọi hoặc loại dữ liệu đang được đọc. Hãy thiết kế cách xử lý `UNDECIDED` rõ ràng; nếu yêu cầu là chỉ cho phép những lớp được nêu tên, có thể bọc composite bằng `rejectUndecidedClass` sau khi bảo đảm filter allowlist trả `ALLOWED` cho các lớp hợp lệ.

### 11.1. Vì sao factory hữu ích?

Giả sử một ứng dụng có:

- Filter toàn JVM để giới hạn tối đa depth, references và bytes.
- Filter của thư viện import để chỉ cho phép DTO nhập liệu.
- Filter của thư viện cache để chỉ cho phép kiểu dữ liệu cache.

Factory có thể kết hợp filter toàn JVM với filter riêng của từng `ObjectInputStream`. Khi đó, filter toàn cục vẫn có quyền từ chối object graph vượt giới hạn, trong khi từng ngữ cảnh giới hạn lớp được phép.

Không nên để một thư viện tùy ý thay thế hoàn toàn chính sách bảo vệ của ứng dụng. Factory là điểm trung tâm để quyết định filter mới được hợp nhất, giữ lại hoặc thay thế theo hợp đồng của hệ thống.

## 12. Thứ tự gọi filter và tác dụng phụ

Về trạng thái, phép kết hợp có tính đối xứng ở kết quả: `merge(A, B)` và `merge(B, A)` cho cùng quy tắc ưu tiên status. Nhưng quá trình thực thi **không hoàn toàn đối xứng**:

- Filter thứ nhất được gọi trước.
- Nếu filter thứ nhất trả `REJECTED`, filter thứ hai không được gọi.
- Nếu filter thứ nhất không từ chối, filter thứ hai mới được gọi.

Do đó, filter nên là hàm kiểm tra thuần, không phụ thuộc vào việc filter khác có được gọi hay không. Tránh ghi dữ liệu nghiệp vụ, tăng bộ đếm dùng cho logic chính hoặc thay đổi trạng thái ứng dụng trong `checkInput`.

Nếu cần ghi log, log nên mang tính quan sát và không làm thay đổi kết quả chính sách. Không được giả định mọi filter luôn được gọi cho mọi đối tượng.

## 13. Những sai lầm khi ghép filter

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `merge` chỉ trả `ALLOWED` khi cả hai filter cùng cho phép | Hiểu sai hợp đồng; chỉ một `ALLOWED` cũng đủ nếu filter kia không từ chối. | Dùng bảng truth table để thiết kế từng filter. |
| Allowlist trả `UNDECIDED` cho lớp không nằm trong danh sách | Một filter khác trả `ALLOWED` có thể khiến lớp đó được chấp nhận. | Dùng `allowFilter(predicate, REJECTED)` cho allowlist chặt. |
| Resource filter trả `ALLOWED` cho mọi object dưới ngưỡng | Có thể làm lớp chưa được allowlist quyết định trở thành `ALLOWED` sau merge. | Trả `UNDECIDED` khi giới hạn không bị vượt. |
| Chỉ dùng blocklist với dữ liệu không tin cậy | Lớp mới hoặc chưa biết vẫn có thể được chấp nhận. | Ưu tiên allowlist theo từng use case. |
| Cho rằng `UNDECIDED` có nghĩa từ chối | Deserialization có thể tiếp tục nếu không có filter khác từ chối. | Dùng `rejectUndecidedClass` khi cần fail-closed cho class. |
| Gọi `merge(null, filter)` | Đối số đầu tiên bắt buộc khác null; phát sinh `NullPointerException`. | Xử lý null trước khi gọi hoặc đặt filter bắt buộc ở vị trí đầu. |
| Dùng `rejectUndecidedClass` với filter chỉ có resource limits | Lớp không được filter nào cho phép có thể bị từ chối hết. | Kết hợp allowlist rõ ràng trước khi chuyển undecided thành reject. |
| Nghĩ `ALLOWED` có thể ghi đè `REJECTED` | Không đúng; `REJECTED` luôn thắng. | Giữ mọi quy tắc từ chối trong filter tổng hợp. |
| Chỉ gắn filter cho một stream nhưng ứng dụng tạo nhiều stream khác | Những stream còn lại có thể không được bảo vệ theo chính sách mong muốn. | Áp dụng filter ở mọi stream hoặc cấu hình factory toàn JVM. |
| Xem filter là validator đầy đủ cho dữ liệu | Filter kiểm tra lớp và metrics, không xác minh toàn bộ invariant nghiệp vụ. | Kiểm tra dữ liệu sau deserialize và tránh Java serialization với dữ liệu không tin cậy khi có thể. |

## 14. Chọn cách kết hợp theo mục tiêu

| Mục tiêu | Thiết kế phù hợp |
| --- | --- |
| Chỉ cho phép một nhóm DTO cụ thể | `allowFilter(predicate, REJECTED)`. |
| Từ chối một nhóm lớp đã biết, còn lớp khác để filter khác quyết định | `rejectFilter(predicate, UNDECIDED)`. |
| Giới hạn depth, references, bytes và array length | Filter metrics trả `REJECTED` khi vượt ngưỡng, nếu không trả `UNDECIDED`. |
| Allowlist cộng resource limits | `merge(allowlist, limits)`. |
| Nhiều allowlist độc lập đều phải chấp nhận lớp | Dùng allowlist strict; `REJECTED` từ một filter sẽ phủ quyết. |
| Mọi lớp chưa được quyết định đều phải bị từ chối | Bọc composite bằng `rejectUndecidedClass` sau khi bảo đảm lớp hợp lệ được `ALLOWED`. |
| Chính sách khác nhau theo thư viện hoặc thread | Dùng filter factory và ghép filter theo context. |
| Chính sách cấu hình bằng chuỗi pattern | `Config.createFilter(...)`, có thể ghép với filter logic khác. |

Trước khi ghép, hãy viết ra mỗi filter chịu trách nhiệm cho điều gì và trạng thái nào nó trả khi không có vấn đề. Đây là bước quan trọng hơn việc chỉ gọi `merge`.

## 15. Ví dụ đọc kết quả từng filter bằng tay

Giả sử có hai filter:

~~~java
ObjectInputFilter classFilter = info -> {
    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }
    if (type == Message.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }
    return ObjectInputFilter.Status.REJECTED;
};

ObjectInputFilter sizeFilter = info -> {
    if (info.streamBytes() > 500_000) {
        return ObjectInputFilter.Status.REJECTED;
    }
    return ObjectInputFilter.Status.UNDECIDED;
};

ObjectInputFilter combined =
    ObjectInputFilter.merge(classFilter, sizeFilter);
~~~

Phân tích:

| Lần kiểm tra | classFilter | sizeFilter | combined |
| --- | --- | --- | --- |
| `Message`, 100 KB | `ALLOWED` | `UNDECIDED` | `ALLOWED` |
| `Message`, 600 KB | `ALLOWED` | `REJECTED` | `REJECTED` |
| `Unexpected`, 100 KB | `REJECTED` | Không được gọi nếu classFilter chạy trước và từ chối | `REJECTED` |
| Không có class, 100 KB | `UNDECIDED` | `UNDECIDED` | `UNDECIDED` |
| Không có class, 600 KB | `UNDECIDED` | `REJECTED` | `REJECTED` |

Trường hợp `Unexpected` cho thấy short-circuit: filter đầu tiên đã từ chối nên filter thứ hai không cần chạy. Trường hợp metrics-only cho thấy filter vẫn có thể quyết định dựa trên kích thước stream dù không có lớp cụ thể ở lần kiểm tra đó.

## 16. Câu hỏi thường gặp

**`ObjectInputFilter.merge` có từ Java mấy?**  
Phương thức này được bổ sung từ Java 17.

**`merge` có phải phép AND không?**  
Không. `REJECTED` từ bất kỳ filter nào đều thắng; nếu không có reject, chỉ cần một filter trả `ALLOWED` thì kết quả là `ALLOWED`; cả hai `UNDECIDED` thì kết quả là `UNDECIDED`.

**Filter thứ hai có được gọi nếu filter đầu tiên trả `REJECTED` không?**  
Không. `merge` trả `REJECTED` ngay sau kết quả của filter đầu tiên.

**Có thể truyền null cho cả hai filter không?**  
Không. Đối số đầu tiên phải khác null. Đối số thứ hai có thể null; khi đó phương thức trả lại filter đầu tiên.

**`UNDECIDED` có chặn lớp không?**  
Không. Trạng thái này có nghĩa filter không đưa ra quyết định. Deserialization có thể tiếp tục nếu không có filter khác từ chối. Dùng `rejectUndecidedClass` nếu cần từ chối lớp chưa được cho phép rõ ràng.

**Tại sao resource filter nên trả `UNDECIDED` khi không vượt giới hạn?**  
Vì filter này chỉ chịu trách nhiệm giới hạn tài nguyên. Nếu nó trả `ALLOWED` cho mọi lớp có kích thước hợp lệ, kết quả merge có thể cho phép một lớp mà allowlist chưa chấp nhận.

**`allowFilter` có sẵn trong Java 17 không?**  
Có. `ObjectInputFilter.allowFilter` được bổ sung từ Java 17; truyền `Status.REJECTED` làm trạng thái khi predicate sai để tạo allowlist strict.

**`rejectUndecidedClass` có từ Java 17 không?**  
Có. Nó chuyển kết quả `UNDECIDED` thành `REJECTED` đối với class, với xử lý đặc biệt cho array và primitive array; lần kiểm tra metrics-only vẫn có thể là `UNDECIDED`.

**`merge` có tự gắn filter vào mọi ObjectInputStream không?**  
Không. Nó chỉ tạo một filter tổng hợp. Ứng dụng phải gắn filter cho stream hoặc cấu hình filter factory để lựa chọn/chia sẻ chính sách phù hợp.

**Có thể dùng merge để bảo vệ dữ liệu không tin cậy hoàn toàn không?**  
Filter giúp giảm rủi ro bằng cách giới hạn lớp và tài nguyên, nhưng không thay thế việc xác thực dữ liệu, kiểm tra invariant nghiệp vụ hoặc lựa chọn định dạng trao đổi an toàn hơn. Tránh deserialize dữ liệu không tin cậy khi có thể.

## 17. Tài liệu tham khảo chính thức

- [Java SE 17 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): hợp đồng `merge`, `allowFilter`, `rejectFilter`, `rejectUndecidedClass`, filter status và filter factory.
- [Java SE 17 API — ObjectInputFilter.Status](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Status.html): ý nghĩa `ALLOWED`, `REJECTED` và `UNDECIDED`.
- [Java SE 17 API — ObjectInputStream.setObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html#setObjectInputFilter(java.io.ObjectInputFilter)): gắn filter cho một object input stream.
- [Java SE 17 API — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): tạo filter từ pattern, cấu hình filter toàn JVM và filter factory.
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): thiết kế filter factory để áp dụng chính sách theo ngữ cảnh.
- [Oracle Secure Coding Guidelines — Serialization and Deserialization](https://www.oracle.com/java/technologies/javase/seccodeguide.html): khuyến nghị bảo vệ ứng dụng khi xử lý serialization/deserialization.

**Nguyên tắc áp dụng:** Chia chính sách thành filter có trách nhiệm rõ ràng, sau đó dùng `ObjectInputFilter.merge` để ghép chúng. Hãy nhớ `REJECTED` luôn phủ quyết, một `ALLOWED` đủ tạo kết quả cho phép nếu không có reject, và `UNDECIDED` không tự động chặn lớp. Với dữ liệu không tin cậy, kết hợp allowlist strict, giới hạn tài nguyên và chính sách từ chối undecided phù hợp với object graph thực tế.

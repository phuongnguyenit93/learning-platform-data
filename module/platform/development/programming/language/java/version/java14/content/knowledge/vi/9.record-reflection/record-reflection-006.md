# Tìm canonical constructor của record từ dãy kiểu thành phần

Khi làm việc với **reflection** trong Java, đôi khi bạn chỉ có đối tượng `Class<?>` của một record và cần tìm đúng **canonical constructor** để tạo instance, sinh mã ánh xạ dữ liệu hoặc kiểm tra metadata. Cách đáng tin cậy là lấy **record components theo đúng thứ tự khai báo**, trích xuất kiểu `Class<?>` của từng component, rồi truyền dãy kiểu đó vào `Class.getDeclaredConstructor(...)`.

Không nên giả định constructor đầu tiên trả về từ `getDeclaredConstructors()` là canonical constructor. Record có thể khai báo thêm constructor nạp chồng, còn thứ tự phần tử trong mảng constructor trả về từ reflection không phải cơ chế xác định canonical constructor.

Từ Java 16, record là tính năng chính thức; các API `Class.isRecord()`, `Class.getRecordComponents()` và `java.lang.reflect.RecordComponent` vẫn được dùng trên Java hiện đại. Các ví dụ dưới đây biên dịch và chạy trên **JDK 17+**, không cần chế độ preview.

## 1. Canonical constructor là gì?

Xét khai báo:

~~~java
record Order(String code, int quantity, java.util.List<String> labels) {}
~~~

Record có ba **record components**, lần lượt:

1. `code` có kiểu khai báo `String`.
2. `quantity` có kiểu khai báo `int`.
3. `labels` có kiểu khai báo `List<String>`.

**Canonical constructor** nhận một tham số cho **mỗi component**, theo **đúng thứ tự của record header**. Vì Java dùng type erasure trong chữ ký JVM, có thể biểu diễn dãy kiểu tham số bằng các `Class<?>` sau:

~~~java
Class<?>[] parameterTypes = {
    String.class,
    int.class,
    java.util.List.class
};
~~~

Đó là dãy kiểu để tra cứu constructor tương ứng với:

~~~java
Order(String code, int quantity, java.util.List<String> labels)
~~~

Đây là **chữ ký minh họa** của canonical constructor, không phải một phương thức Java độc lập. Kiểu `List<String>` tại mức source tương ứng `List.class` khi tìm constructor qua reflection; không tồn tại cú pháp `List<String>.class` hợp lệ.

Record có thể có:

- **Canonical constructor ngầm định**, khi không viết constructor chính.
- **Compact canonical constructor**, ví dụ `Order { ... }`, có tham số ngầm định theo record header.
- **Canonical constructor viết đầy đủ**, khai báo các tham số và tự khởi tạo component fields.
- **Constructor nạp chồng** nhận dãy tham số khác, nhưng theo quy tắc record, constructor không phải canonical phải ủy quyền cho constructor khác của cùng record bằng `this(...)` để cuối cùng tới canonical constructor.

Ba hình thức đầu đều biểu thị **một vai trò canonical** cho record, không phải ba constructor khác nhau có thể đồng thời tồn tại cùng chữ ký.

### Quan hệ giữa component và tham số

| Metadata | Ý nghĩa | Ví dụ cho `Order` |
|---|---|---|
| `RecordComponent.getName()` | Tên component trong record header | `code`, `quantity`, `labels` |
| `RecordComponent.getType()` | Kiểu thành phần sau erasure, dưới dạng `Class<?>` | `String.class`, `int.class`, `List.class` |
| `RecordComponent.getGenericType()` | Thông tin kiểu khai báo có generic, dưới dạng `Type` | `List<String>` có thể được phản ánh là `ParameterizedType` |
| `Class.getDeclaredConstructor(Class<?>...)` | Tìm constructor có dãy kiểu tham số đúng thứ tự | Ba kiểu `String, int, List` |
| `Constructor.getParameterCount()` | Số lượng tham số của constructor đã tìm | `3` |

Tên component được dùng để làm việc với dữ liệu và tài liệu hóa, nhưng **không phải tham số đầu vào của `getDeclaredConstructor`**; việc tra cứu ở API này căn cứ dãy **kiểu**.

## 2. Quy trình tìm canonical constructor qua reflection

Thực hiện năm bước:

1. Nhận một `Class<?> recordClass` và kiểm tra khác `null`.
2. Kiểm tra `recordClass.isRecord()` để chắc chắn đây là record. Đối với lớp thông thường, khái niệm “canonical constructor của record” không áp dụng.
3. Gọi `recordClass.getRecordComponents()`. Với một record, kết quả là mảng các `RecordComponent` theo **đúng thứ tự được khai báo trong record header**.
4. Lấy `getType()` cho từng phần tử để tạo `Class<?>[]` đúng thứ tự. Không sắp xếp theo tên và không dùng dãy field tự lấy từ `getDeclaredFields()`.
5. Gọi `recordClass.getDeclaredConstructor(parameterTypes)`. Kết quả là `Constructor<?>` đại diện cho canonical constructor nếu tìm thấy.

Hàm tiện ích:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.Objects;

public final class RecordConstructorLookup {

    private RecordConstructorLookup() {}

    public static Constructor<?> findCanonical(Class<?> recordClass)
            throws NoSuchMethodException {
        Objects.requireNonNull(recordClass, "recordClass");

        if (!recordClass.isRecord()) {
            throw new IllegalArgumentException(
                    "Not a record: " + recordClass.getName()
            );
        }

        RecordComponent[] components =
                recordClass.getRecordComponents();

        Class<?>[] parameterTypes = Arrays.stream(components)
                .map(RecordComponent::getType)
                .toArray(Class<?>[]::new);

        return recordClass.getDeclaredConstructor(parameterTypes);
    }
}
~~~

Lớp trên **độc lập và biên dịch được**, nhưng chưa có `main`; nó là utility được gọi từ chương trình khác. Giữ hàm `findCanonical` đủ hẹp: hàm chỉ tìm metadata, không tự mở quyền truy cập và không khởi tạo instance.

**Tại sao dùng `getDeclaredConstructor`?** API này tìm cả constructor được khai báo với mức truy cập không công khai. Ngược lại, `getConstructor(...)` chỉ tìm các constructor `public`. Khả năng **tìm thấy** một constructor không đồng nghĩa được phép **gọi** constructor đó từ mọi package hay module.

## 3. Ví dụ Java 17+ đầy đủ: tìm, phân biệt overload và tạo record

Tạo file **`CanonicalRecordLookupDemo.java`**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Modifier;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class CanonicalRecordLookupDemo {

    public record Order(String code, int quantity, List<String> labels) {

        public Order {
            code = Objects.requireNonNull(code, "code").strip();
            if (code.isBlank()) {
                throw new IllegalArgumentException("code is blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            labels = List.copyOf(labels);
        }

        // Constructor nạp chồng: không phải canonical constructor.
        public Order(String code) {
            this(code, 1, List.of());
        }
    }

    static Constructor<?> findCanonical(Class<?> type)
            throws NoSuchMethodException {
        Objects.requireNonNull(type, "type");

        if (!type.isRecord()) {
            throw new IllegalArgumentException(
                    "Not a record: " + type.getName()
            );
        }

        RecordComponent[] components = type.getRecordComponents();
        Class<?>[] signature = Arrays.stream(components)
                .map(RecordComponent::getType)
                .toArray(Class<?>[]::new);

        return type.getDeclaredConstructor(signature);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<?> type = Order.class;
        System.out.println("isRecord=" + type.isRecord());

        RecordComponent[] components = type.getRecordComponents();
        for (RecordComponent component : components) {
            System.out.println(
                    "component=" + component.getName()
                    + ":" + component.getType().getTypeName()
            );
        }

        Constructor<?> canonical = findCanonical(type);
        System.out.println(
                "canonicalParameters=" + canonical.getParameterCount()
        );
        System.out.println(
                "canonicalPublic="
                + Modifier.isPublic(canonical.getModifiers())
        );

        Constructor<?> overload =
                type.getDeclaredConstructor(String.class);
        System.out.println(
                "overloadParameters=" + overload.getParameterCount()
        );

        Object created = canonical.newInstance(
                "  A-7  ", 2, List.of("java", "record")
        );
        System.out.println("created=" + created);

        try {
            canonical.newInstance("   ", 2, List.of());
        } catch (InvocationTargetException ex) {
            Throwable cause = ex.getCause();
            System.out.println(
                    "invalid=" + cause.getClass().getSimpleName()
                    + ":" + cause.getMessage()
            );
        }
    }
}
~~~

Chạy trong thư mục chứa file, dùng JDK 17 hoặc mới hơn có hỗ trợ `--release 17`:

~~~bash
javac --release 17 CanonicalRecordLookupDemo.java
java CanonicalRecordLookupDemo
~~~

**Standard output dự kiến chính xác:**

~~~text
isRecord=true
component=code:java.lang.String
component=quantity:int
component=labels:java.util.List
canonicalParameters=3
canonicalPublic=true
overloadParameters=1
created=Order[code=A-7, quantity=2, labels=[java, record]]
invalid=IllegalArgumentException:code is blank
~~~

### Giải thích kết quả từng bước

- `Order.class.isRecord()` trả `true` vì `Order` là một record.
- `getRecordComponents()` trả ba component đúng thứ tự header. `getType().getTypeName()` in `java.lang.String`, `int` và `java.util.List`. Tham số generic `String` trong `List<String>` không làm dãy kiểu Class chứa một kiểu `List<String>.class`.
- `findCanonical` dùng ba kiểu đó để tìm constructor `Order(String, int, List)`, dù phần triển khai của nó viết dạng **compact constructor**.
- `canonical.getParameterCount()` là `3`; `Modifier.isPublic(...)` là `true` vì ví dụ chủ động khai báo `public Order { ... }`.
- Constructor nạp chồng `Order(String)` nhận một tham số và được tìm bằng một chữ ký khác; nó không phải canonical constructor.
- `canonical.newInstance(...)` **thực thi constructor thật sự**. Chuỗi mã được `strip()` thành `A-7`; danh sách được sao chép bằng `List.copyOf`; record tạo thành công nên `toString()` in các component đã lưu.
- Lần tạo thứ hai dùng `"   "`. Compact constructor phát hiện mã rỗng sau `strip()` và ném `IllegalArgumentException`. Khi đi qua `Constructor.newInstance`, ngoại lệ do constructor ném được bọc trong `InvocationTargetException`; `getCause()` cung cấp lỗi gốc.

**Hai khái niệm khác nhau:** `getDeclaredConstructor(...)` chỉ lấy đối tượng metadata của constructor; `newInstance(...)` mới thực sự gọi constructor và tạo đối tượng (hoặc ném ngoại lệ). Phép tra cứu không tự chạy validation hoặc các tác dụng phụ trong constructor.

## 4. Tại sao phải dùng đúng thứ tự component?

Chữ ký constructor dựa trên **dãy có thứ tự**, không dựa trên tập kiểu không có thứ tự. Ví dụ:

~~~java
record Position(int x, long y) {}
~~~

Canonical constructor có dãy tham số `(int, long)`. Dãy sau là chính xác:

~~~java
Position.class.getDeclaredConstructor(int.class, long.class);
~~~

Nhưng dãy này không phải cùng chữ ký:

~~~java
// Nếu không khai báo constructor khác phù hợp, sẽ ném NoSuchMethodException.
Position.class.getDeclaredConstructor(long.class, int.class);
~~~

Ba đoạn trên là **đoạn minh họa**; trong chương trình hoàn chỉnh cần xử lý hoặc khai báo ngoại lệ reflection phù hợp.

Ngay cả khi hai component có **cùng kiểu**, thứ tự vẫn mang ý nghĩa dữ liệu:

~~~java
record Range(int start, int end) {}
~~~

Ở đây dãy kiểu là `(int, int)`. Reflection tìm đúng constructor bằng dãy kiểu nhưng **không biết** đối số đầu đang có ý nghĩa “start” hay “end”. Tầng ánh xạ dữ liệu phải gắn giá trị theo **tên và thứ tự component**; nếu truyền `end` trước `start`, việc tra cứu vẫn thành công nhưng đối tượng có thể sai nghiệp vụ.

**Không dùng `getDeclaredFields()` để suy ra chữ ký.** Một record có thể khai báo các trường `static` bổ sung và hệ thống reflection cho field không phải API được thiết kế để mô tả thứ tự record components. `getRecordComponents()` mới là nguồn dành riêng cho record header.

Cũng không được tự sắp xếp các component theo bảng chữ cái hay thứ tự field; thứ tự record header là hợp đồng của canonical constructor.

## 5. Vì sao `getType()` chứ không phải `getGenericType()`?

`RecordComponent.getType()` trả về `Class<?>` biểu thị kiểu **sau erasure**. `RecordComponent.getGenericType()` trả về `java.lang.reflect.Type`, có thể phản ánh tham số kiểu như `List<String>`.

Ví dụ:

~~~java
import java.util.List;

record Labels(List<String> values) {}
~~~

Với component `values`:

- `getName()` → `"values"`.
- `getType()` → `List.class`.
- `getGenericType()` biểu diễn `List<String>`, thường dưới dạng một `ParameterizedType`.

`Class.getDeclaredConstructor(...)` đòi các đối tượng `Class<?>`; không nhận `ParameterizedType` hoặc chuỗi mô tả generic. Vì vậy mã đúng là:

~~~java
RecordComponent[] components = Labels.class.getRecordComponents();
Class<?>[] signature = {
    components[0].getType()
};
Constructor<?> ctor = Labels.class.getDeclaredConstructor(signature);
~~~

Đoạn này minh họa nơi đã import `java.lang.reflect.Constructor` và `RecordComponent`, và cần xử lý `NoSuchMethodException`. Nó tra cứu constructor có một tham số `List`.

Với record generic:

~~~java
record Box<T>(T value) {}
record NumberBox<T extends Number>(T value) {}
~~~

Dãy `Class<?>` dùng cho canonical constructor lần lượt chứa `Object.class` (vì `T` không có bound tường minh) và `Number.class` (vì `T extends Number`). Đây là hệ quả của erasure; không dùng `T.class` hay lớp của dữ liệu thực tế bên trong instance để đoán chữ ký.

**Ứng dụng thực tế:** Khi cần biết cấu trúc generic để deserialize dữ liệu, dùng `getGenericType()` làm thông tin bổ sung. Khi cần **tìm constructor**, dùng `getType()`. Hai API phục vụ hai công việc khác nhau.

## 6. Những trường hợp đặc biệt vẫn áp dụng cùng thuật toán

### 6.1. Record không có component

~~~java
record Empty() {}
~~~

`getRecordComponents()` trả một mảng có độ dài `0`. Dãy kiểu constructor là mảng rỗng; canonical constructor không có tham số. Có thể gọi:

~~~java
Constructor<?> ctor =
        Empty.class.getDeclaredConstructor(new Class<?>[0]);
~~~

Đây là đoạn minh họa đã import `Constructor` và có xử lý ngoại lệ phù hợp. Không cần trường hợp đặc biệt khi xây dựng `Class<?>[]` bằng stream: stream rỗng sẽ tạo mảng rỗng.

### 6.2. Component có kiểu nguyên thủy

~~~java
record Temperature(int degrees) {}
~~~

`getType()` trả `int.class`, không phải `Integer.class`. `getDeclaredConstructor(Integer.class)` sẽ không khớp chữ ký canonical `(int)` nếu record chỉ có constructor đó. Khi gọi `Constructor.newInstance` với đối số kiểu `Integer` được boxing từ một literal `int`, reflection có thể thực hiện chuyển đổi unboxing phù hợp; **chữ ký tra cứu** vẫn là `int.class`.

### 6.3. Component là mảng hoặc varargs

~~~java
record Names(String... values) {}
~~~

Record component `values` có kiểu mảng `String[]`. `getType()` trả `String[].class`; canonical constructor tại bytecode nhận một tham số kiểu `String[]`. Vì vậy:

~~~java
Constructor<?> ctor =
        Names.class.getDeclaredConstructor(String[].class);
Object result = ctor.newInstance(
        (Object) new String[] {"A", "B"}
);
~~~

Đoạn này minh họa với import `Constructor` và xử lý ngoại lệ phù hợp. Ép `(Object)` giúp truyền cả `String[]` như **một đối số** cho phương thức varargs `Constructor.newInstance(Object...)`, tránh trình biên dịch hiểu các phần tử mảng thành các đối số phản chiếu riêng.

### 6.4. Record có constructor nạp chồng

~~~java
record Money(long cents, String currency) {
    Money(long cents) {
        this(cents, "VND");
    }
}
~~~

Canonical constructor có chữ ký `(long, String)`; constructor nạp chồng có chữ ký `(long)`. `getDeclaredConstructors()` có thể trả cả hai nhưng thứ tự của mảng không phải chỉ báo cái nào là canonical. Lấy components `cents` và `currency` rồi tra dãy `long.class`, `String.class` sẽ xác định đúng constructor chính.

### 6.5. Record có compact constructor

~~~java
record Count(int value) {
    Count {
        if (value < 0) {
            throw new IllegalArgumentException("negative");
        }
    }
}
~~~

Dù constructor chỉ khai báo `Count { ... }`, canonical constructor vẫn có một tham số `int`. `Count.class.getDeclaredConstructor(int.class)` tìm thấy constructor đó. Khi gọi phản chiếu với giá trị âm, validation vẫn chạy và có thể ném ngoại lệ.

## 7. Phân biệt tìm constructor và quyền gọi constructor

Hai API quan trọng:

| API | Phạm vi tra cứu | Lưu ý khi sử dụng |
|---|---|---|
| `getDeclaredConstructor(parameterTypes)` | Constructor **khai báo trong chính class**, gồm cả không public | Tìm được đối tượng `Constructor` không có nghĩa luôn được phép gọi |
| `getConstructor(parameterTypes)` | Constructor `public` có chữ ký tương ứng | Không phù hợp để xác định canonical constructor không public |

Trong thiết kế thư viện/API công khai, ưu tiên record công khai và canonical constructor công khai khi ứng dụng bên ngoài cần tạo instance qua reflection. Nếu record là lớp lồng không public hoặc thuộc module không mở quyền phản chiếu, `getDeclaredConstructor` có thể tìm thấy metadata nhưng `newInstance` vẫn gặp vấn đề quyền truy cập.

Khi xử lý dữ liệu ngoài module, không xem `setAccessible(true)` là giải pháp chung: từ cơ chế module Java hiện đại, yêu cầu mở quyền có thể bị từ chối. Hãy dùng API công khai, cân nhắc cấu hình `opens` có chủ đích khi thực sự cần deep reflection, và xử lý lỗi truy cập một cách minh bạch.

Reflection cũng không thay quy tắc kiểm tra dữ liệu trong constructor. Một canonical/compact constructor có thể từ chối đầu vào sai bằng ngoại lệ; dùng reflection không bỏ qua validation.

## 8. Các lỗi phổ biến và cách sửa

| Lỗi | Vì sao | Cách sửa |
|---|---|---|
| Lấy `getDeclaredConstructors()[0]` làm canonical | Thứ tự constructor reflection không phải hợp đồng để xác định constructor chính | Lấy dãy kiểu từ `getRecordComponents()` rồi gọi `getDeclaredConstructor(...)` |
| Sắp xếp components theo tên | Chữ ký phụ thuộc thứ tự header, không phụ thuộc bảng chữ cái | Giữ nguyên thứ tự mảng trả về |
| Dùng `getDeclaredFields()` thay `getRecordComponents()` | Có thể gặp field khác hoặc suy luận sai thứ tự/ý nghĩa | Dùng metadata chuyên biệt cho record |
| Dùng `getGenericType()` làm tham số tra cứu | Trả `Type`, không nhất thiết là `Class<?>`; chữ ký JVM đã erasure | Dùng `getType()` để xây `Class<?>[]` |
| Dùng `Integer.class` cho component `int` | `Class<?>` sai với chữ ký `int` | Dùng đúng `int.class` do `getType()` cung cấp |
| Dùng `List<String>.class` | Java không có class literal cho kiểu generic tham số hóa | Dùng `List.class` |
| Quên record không có component | Canonical constructor vẫn tồn tại với 0 tham số | Truyền mảng `Class<?>[0]` |
| Xem constructor nạp chồng là canonical | Chữ ký nạp chồng có thể có số/thứ tự kiểu khác | Khớp chính xác tất cả component types |
| Cho rằng tìm được là gọi được | Kiểm soát truy cập ở reflection/module vẫn áp dụng | Xác định quyền gọi, dùng API công khai hoặc mở module có chủ đích |
| Quên xử lý ngoại lệ do constructor ném | `newInstance` bọc lỗi của constructor trong `InvocationTargetException` | Kiểm tra `getCause()` và phân biệt lỗi dữ liệu với lỗi reflection |
| Truyền mảng vào `newInstance` thiếu ép kiểu | Varargs có thể bị trải thành nhiều đối số | Ép `(Object)` khi muốn một tham số mảng |

### Khi bị `NoSuchMethodException`, hãy kiểm tra

1. Lớp đích có đúng là record được xác nhận bằng `isRecord()` không?
2. Dãy kiểu có đủ số components và đúng thứ tự không?
3. Kiểu primitive có đúng `int.class`/`long.class`, hay nhầm với wrapper?
4. Generic đã được xử lý erasure đúng chưa?
5. Mảng/varargs đã dùng kiểu array thay vì element type chưa?
6. Bạn đang gọi `getConstructor` (chỉ public) hay `getDeclaredConstructor`?

Nếu lấy dãy kiểu trực tiếp từ `getRecordComponents()` của **chính record class** rồi dùng `getDeclaredConstructor(...)`, các lỗi về thứ tự, erasure và thiếu tham số thường được tránh hoàn toàn. Nếu việc tra cứu vẫn thất bại, cần ghi nhận và kiểm tra nguyên nhân thực tế; không nên tự ý chọn constructor khác.

## 9. Ứng dụng: dựng dữ liệu đầu vào theo thứ tự component

Một framework ánh xạ dữ liệu thường làm hai việc khác nhau:

- **Xác định constructor đúng:** lấy `Class<?>[]` từ `getRecordComponents()` và gọi `getDeclaredConstructor(...)`.
- **Chuẩn bị đối số đúng:** lấy tên `getName()` cùng kiểu `getType()` để ánh xạ từng trường dữ liệu vào **đúng vị trí** trong mảng `Object[]`.

Ví dụ minh họa cho record `Order(String code, int quantity, List<String> labels)` ở phần trước:

~~~java
Object[] arguments = {
    "A-7",
    2,
    java.util.List.of("java", "record")
};
Object created = findCanonical(Order.class).newInstance(arguments);
~~~

Đây là **đoạn mã minh họa**: `Order`, `findCanonical` phải nằm trong phạm vi và phải xử lý các ngoại lệ reflection. Dãy `arguments` phải khớp với thứ tự `code`, `quantity`, `labels` trong record header.

Điểm quan trọng là bước “tìm constructor” và bước “chuẩn bị giá trị” không được trộn lẫn. Bạn có thể tìm đúng canonical constructor nhưng vẫn tạo đối tượng sai nếu đưa dữ liệu vào sai vị trí, truyền nhầm loại giá trị, không xử lý `null` hoặc không tôn trọng validation của record.

Với lớp generic, thông tin `getGenericType()` có thể hỗ trợ framework giải mã kiểu phần tử, song đối số cuối đưa cho reflection vẫn phải tương thích với các kiểu tham số runtime. Với trường phức tạp, cần quy tắc chuyển đổi dữ liệu riêng; `Constructor.newInstance` không tự parse JSON hay tự biến mọi chuỗi thành số/collection.

## 10. Bài tập và tự kiểm tra

**Câu 1.** Record sau có chữ ký canonical constructor nào?

~~~java
record Event(long id, String type, boolean active) {}
~~~

**Đáp án:** `(long, String, boolean)`; mảng kiểu dùng để tra là `{long.class, String.class, boolean.class}`, đúng thứ tự trong header.

**Câu 2.** Record `record Tags(java.util.List<String> values) {}` cần truyền `List<String>.class` hay `List.class` vào `getDeclaredConstructor`?

**Đáp án:** `List.class`. `getType()` trả `Class<?>` sau erasure, còn thông tin `List<String>` có thể đọc bằng `getGenericType()`.

**Câu 3.** Một record có constructor `R(String, int)` và `R(String)`. Có nên lấy constructor đầu tiên của `getDeclaredConstructors()` không?

**Đáp án:** Không. Lấy kiểu của từng record component theo thứ tự rồi tìm bằng `getDeclaredConstructor(...)`. Constructor nạp chồng không được mặc định xem là canonical.

**Câu 4.** Nếu `getDeclaredConstructor` trả về constructor `private`, có chắc `newInstance` gọi được ở mọi nơi không?

**Đáp án:** Không. Reflection vẫn chịu quy tắc truy cập và ràng buộc module. Khả năng đọc metadata khác với quyền thực thi constructor.

**Câu 5.** `record Empty() {}` có canonical constructor không?

**Đáp án:** Có, canonical constructor không tham số. `getRecordComponents()` là mảng rỗng và `getDeclaredConstructor()` tìm constructor không tham số.

**Câu 6.** Nếu gọi canonical constructor của `Order` qua reflection và constructor ném `IllegalArgumentException` thì bên gọi thường nhận loại ngoại lệ phản chiếu nào?

**Đáp án:** `InvocationTargetException` bao quanh ngoại lệ thực tế; dùng `getCause()` để xác định `IllegalArgumentException` và thông điệp kiểm tra dữ liệu.

**Câu 7.** Với `record Point(int x, int y) {}`, reflection có đủ thông tin để xác định đối số nào là `x` và đối số nào là `y` không?

**Đáp án:** Có thể lấy tên và thứ tự từ `RecordComponent[]` để ánh xạ dữ liệu; chỉ dãy kiểu `(int, int)` thì **không đủ** để phân biệt ý nghĩa hai tham số khi chuẩn bị giá trị.

## 11. Quy tắc ghi nhớ

**Thuật toán chuẩn:**

~~~java
RecordComponent[] components = recordClass.getRecordComponents();
Class<?>[] parameterTypes = Arrays.stream(components)
        .map(RecordComponent::getType)
        .toArray(Class<?>[]::new);
Constructor<?> canonical =
        recordClass.getDeclaredConstructor(parameterTypes);
~~~

Đây là đoạn mã **trong ngữ cảnh** đã kiểm tra `recordClass.isRecord()`, có import `RecordComponent`, `Arrays`, `Constructor` và xử lý `NoSuchMethodException`. Không sắp xếp components, không suy chữ ký từ fields, không chọn constructor theo vị trí trong mảng, và dùng `getType()` thay cho `getGenericType()` khi gọi `getDeclaredConstructor`.

### Tài liệu tham khảo

- [Java SE 17 API — `Class.isRecord()` và `getRecordComponents()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): API nhận diện và lấy metadata record components.
- [Java SE 17 API — `RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html): tên, kiểu, generic type và accessor của mỗi component.
- [Java SE 17 API — `Class.getDeclaredConstructor(...)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getDeclaredConstructor(java.lang.Class...)): phương thức tìm constructor theo dãy kiểu.
- [Java Language Specification 17 — Record Constructors, `8.10.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): định nghĩa canonical constructor và compact constructor.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): record là tính năng chính thức từ Java 16.

Chỉ cần nhớ rằng **dãy kiểu component từ record header chính là chữ ký để tìm canonical constructor**. Reflection tìm chính xác constructor theo dãy `Class<?>` có thứ tự; việc kiểm tra đầu vào, quyền gọi và tạo instance là những bước riêng cần xử lý sau đó.
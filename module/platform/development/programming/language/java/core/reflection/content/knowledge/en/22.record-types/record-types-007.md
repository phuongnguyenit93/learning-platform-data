# Accessor được khai báo tường minh và metadata thực tế của record

## 1. Accessor của record là một phương thức thực sự

Với `record Label(String text)`, component `text` có một phương thức truy cập cùng tên: `text()`. Nếu tác giả không khai báo nó, compiler cung cấp phần thực hiện trả về giá trị component field.

Tác giả cũng có thể khai báo accessor tường minh trong phần thân record. Khi đó, phương thức ấy chính là accessor của component; không có thêm một accessor ngầm định khác cùng chữ ký để Reflection lựa chọn.

Điều này tạo ra ba lớp thông tin cần phân biệt:

- **RecordComponent:** tên, kiểu, annotation và thông tin về component trong phần đầu record.
- **Method accessor:** phương thức truy cập thực tế, cùng metadata và phần thực hiện của nó.
- **Component field:** nơi lưu giá trị tương ứng, có đặc tính `private final`.

`RecordComponent.getAccessor()` nối component với đúng đối tượng `Method` mô tả accessor của nó. API này không bảo đảm accessor chỉ làm một phép đọc field đơn giản nếu tác giả đã tự viết phần thân.

## 2. Quy tắc của accessor tường minh

Accessor tường minh của một component phải:

- Có cùng tên với component.
- Là phương thức instance `public`.
- Không có tham số.
- Có kiểu trả về giống kiểu khai báo của component.
- Không khai báo tham số kiểu của riêng phương thức.
- Không có mệnh đề `throws`.

Ví dụ một khai báo hợp lệ về mặt ngôn ngữ:

~~~java
record Measurement(int value) {
    public int value() {
        return value;
    }
}
~~~

Đây là một khai báo record, không phải chương trình có `main`.

Không đổi accessor thành `getValue()` theo quy ước JavaBean rồi cho rằng nó thay thế `value()`. Một method khác tên chỉ là method khác của record. Tương tự, một overload như `value(int scale)` không phải accessor của component `value`.

Accessor được tự viết không nhất thiết ghi đè một phương thức từ lớp cha hoặc interface. Tuy vậy, Java có quy tắc riêng cho record: **được phép đặt `@Override` trên accessor tường minh của một component**, kể cả khi không có phương thức tương ứng trong kiểu cha. Annotation này giúp trình biên dịch phát hiện khi component bị đổi tên hoặc loại bỏ mà phương thức cũ không còn là accessor. Quy tắc được nêu tại [JLS §9.6.4.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.4.4).

## 3. Ví dụ: metadata xác định accessor, lời gọi chạy phần thân thực tế

Ví dụ dưới cố ý đặt việc chuẩn hóa chuỗi trong accessor để quan sát sự khác biệt giữa giá trị lưu và giá trị trả về. Thiết kế `Label` trong ví dụ không giữ được quy tắc sao chép của record; phần sau sẽ chỉ ra cách sửa.

Lưu thành `ExplicitAccessorBehaviorDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;
import java.util.Locale;
import java.util.Objects;

public class ExplicitAccessorBehaviorDemo {
    public record Label(String text) {
        public String text() {
            return text.strip().toUpperCase(Locale.ROOT);
        }
    }

    public record NormalizedLabel(String text) {
        public NormalizedLabel {
            text = Objects.requireNonNull(text, "text")
                    .strip().toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Label> type = Label.class;
        RecordComponent component = type.getRecordComponents()[0];
        Method accessor = component.getAccessor();
        Label original = new Label("  lan  ");

        System.out.println("component=" + component.getName());
        System.out.println("accessor=" + accessor.getName());
        System.out.println("parameters=" + accessor.getParameterCount());
        System.out.println("return=" + accessor.getReturnType().getSimpleName());
        System.out.println("sameMethod="
                + accessor.equals(type.getDeclaredMethod("text")));
        System.out.println("synthetic=" + accessor.isSynthetic());
        System.out.println("viaAccessor=[" + accessor.invoke(original) + "]");

        Field field = type.getDeclaredField(component.getName());
        field.setAccessible(true);
        System.out.println("viaField=[" + field.get(original) + "]");

        Label copy = new Label(original.text());
        System.out.println("copyEquals=" + original.equals(copy));

        NormalizedLabel normalized = new NormalizedLabel("  lan  ");
        NormalizedLabel normalizedCopy =
                new NormalizedLabel(normalized.text());
        System.out.println("normalized=[" + normalized.text() + "]");
        System.out.println("normalizedCopyEquals="
                + normalized.equals(normalizedCopy));
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 ExplicitAccessorBehaviorDemo.java
java ExplicitAccessorBehaviorDemo
~~~

Kết quả:

~~~text
component=text
accessor=text
parameters=0
return=String
sameMethod=true
synthetic=false
viaAccessor=[LAN]
viaField=[  lan  ]
copyEquals=false
normalized=[LAN]
normalizedCopyEquals=true
~~~

Các cặp dấu ngoặc vuông giúp nhìn rõ khoảng trắng trong giá trị field. Accessor tường minh trả `LAN`, còn field vẫn chứa chuỗi `"  lan  "` được đưa vào constructor.

`getAccessor()` trả metadata của phương thức `text()` thực tế. So sánh bằng `Method.equals` với phương thức tìm được từ `getDeclaredMethod("text")` cho kết quả đúng. Không dùng `==` để yêu cầu hai lần lấy metadata phải trả cùng một tham chiếu đối tượng `Method`.

Lời gọi `accessor.invoke(original)` chạy phần thân đã được tác giả viết. Reflection không bỏ qua phần chuẩn hóa để đọc thẳng field.

Việc bật truy cập field trong ví dụ chỉ phục vụ quan sát giá trị lưu trong cùng lớp ngoài; không có thao tác ghi field. Một công cụ sử dụng giao diện công khai của record không nên mặc định thay lời gọi accessor bằng đọc private field.

## 4. Hệ quả đối với hợp đồng của record

Các phần thực hiện mặc định của `equals`, `hashCode` và `toString` dựa trên component field, không gọi accessor tường minh để lấy một giá trị đã biến đổi.

Record cần giữ quy tắc sao chép: nếu tạo một record mới bằng các giá trị nhận từ accessor của record cũ, hai record phải bằng nhau theo `equals`.

Trong `Label` của ví dụ:

1. Đối tượng ban đầu lưu `"  lan  "`.
2. Accessor trả `"LAN"`.
3. Bản sao được tạo từ accessor lưu `"LAN"`.
4. `equals` mặc định so sánh hai giá trị field khác nhau, nên trả `false`.

Mã ấy biên dịch được nhưng thiết kế làm mất quy tắc sao chép. Compiler không kiểm chứng được mọi hành vi của accessor do tác giả viết.

`NormalizedLabel` chuyển bước chuẩn hóa vào compact constructor. Giá trị lưu ngay từ đầu đã là `LAN`; accessor ngầm định trả đúng giá trị đó. Bản sao đi qua cùng quy tắc chuẩn hóa và vẫn bằng đối tượng ban đầu.

Nếu chỉ cần một chuỗi hiển thị khác, một lựa chọn rõ ràng là giữ accessor trả dữ liệu component và thêm phương thức có tên riêng cho biểu diễn hiển thị. Dù chọn cách nào, tác giả phải xét sự nhất quán với constructor và các method đặc trưng của record.

Metadata như tên và kiểu trả về không đủ để chứng minh accessor “chỉ đọc field”. Một method có thể tính toán, ném ngoại lệ không kiểm tra hoặc thực hiện tác vụ khác mà vẫn có cùng chữ ký.

## 5. Annotation của component và annotation của accessor là hai nơi khác nhau

Annotation trên phần đầu record có thể được truyền sang các thành viên được khai báo ngầm định nếu `@Target` cho phép. Với **accessor được khai báo tường minh**, annotation trên component không tự được truyền sang method ấy.

Vì vậy, việc thêm một accessor tường minh có thể làm thay đổi metadata method quan sát được, dù tên component và kiểu component vẫn như cũ.

Lưu thành `ExplicitAccessorAnnotationsDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;

public class ExplicitAccessorAnnotationsDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.RECORD_COMPONENT, ElementType.METHOD})
    public @interface HeaderTag {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface AccessorTag {
        String value();
    }

    public record Implicit(
            @HeaderTag("from-header") String text) {
    }

    public record Explicit(
            @HeaderTag("from-header") String text) {

        @AccessorTag("from-method")
        public String text() {
            return text;
        }
    }

    private static void report(Class<?> recordType) {
        RecordComponent component = recordType.getRecordComponents()[0];
        Method accessor = component.getAccessor();

        System.out.println(recordType.getSimpleName()
                + ": componentHeader="
                + component.isAnnotationPresent(HeaderTag.class)
                + ", accessorHeader="
                + accessor.isAnnotationPresent(HeaderTag.class)
                + ", accessorOwn="
                + accessor.isAnnotationPresent(AccessorTag.class));
    }

    public static void main(String[] args) {
        report(Implicit.class);
        report(Explicit.class);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ExplicitAccessorAnnotationsDemo.java
java ExplicitAccessorAnnotationsDemo
~~~

Kết quả:

~~~text
Implicit: componentHeader=true, accessorHeader=true, accessorOwn=false
Explicit: componentHeader=true, accessorHeader=false, accessorOwn=true
~~~

Giải thích:

- `HeaderTag` được phép xuất hiện trên component và trên method, đồng thời giữ lại ở runtime.
- Cả hai component đều có `HeaderTag`.
- Accessor ngầm định của `Implicit` nhận annotation được truyền từ component.
- Accessor tường minh của `Explicit` không tự nhận `HeaderTag`; nó có `AccessorTag` được viết trực tiếp trên method.

Nếu một framework đọc annotation từ accessor, việc tác giả thêm method tường minh có thể làm framework không còn thấy annotation cũ ở method. Điều đó không có nghĩa annotation đã biến mất khỏi component.

Nếu hợp đồng yêu cầu accessor tường minh cũng có cùng annotation, tác giả có thể khai báo annotation tại method khi `@Target` cho phép. Một công cụ cũng có thể đọc đồng thời các vị trí theo chính sách đã định, nhưng không nên giả định mọi vị trí luôn chứa cùng dữ liệu.

## 6. Chọn đúng API cho loại metadata cần dùng

| Thông tin cần lấy | API phù hợp |
| --- | --- |
| Tên component trong phần đầu record | `RecordComponent.getName()` |
| Kiểu component ở mức Class | `RecordComponent.getType()` |
| Kiểu generic của component | `RecordComponent.getGenericType()` |
| Annotation khai báo trên component ở runtime | `RecordComponent.getAnnotations()` hoặc `getAnnotation(...)` |
| Metadata kiểu được chú thích của component | `RecordComponent.getAnnotatedType()` |
| Method accessor thực tế | `RecordComponent.getAccessor()` |
| Annotation của method accessor thực tế | `Method.getAnnotations()` hoặc `getAnnotation(...)` |
| Metadata kiểu trả về được chú thích của accessor | `Method.getAnnotatedReturnType()` |
| Giá trị do accessor cung cấp cho một instance | `Method.invoke(instance)` |

Annotation khai báo và annotation dùng trên kiểu (`TYPE_USE`) cũng là hai khía cạnh cần đọc bằng API tương ứng. Khi accessor được viết tường minh, hãy quan sát metadata của method và kiểu trả về thực tế; không tự suy ra rằng chúng đã được sao chép từ component.

Với generic, `getType()`/`getReturnType()` cho thông tin ở mức `Class`, còn `getGenericType()`/`getGenericReturnType()` giữ mô tả generic phù hợp. Không dùng một chuỗi tên kiểu đã rút gọn làm bằng chứng rằng toàn bộ metadata ở hai vị trí đều giống nhau.

Nên giữ thông tin nguồn của annotation khi tổng hợp: annotation đến từ component hay từ method? Nếu cả hai nơi có cùng loại annotation nhưng giá trị khác nhau, công cụ phải có quy tắc ưu tiên hoặc báo xung đột rõ ràng.

Không có một quy tắc gộp chung phù hợp cho mọi thư viện. Một bộ xử lý cấu trúc record có thể lấy component làm điểm chính; một bộ xử lý method công khai có thể dùng method làm điểm chính. Cả hai phải thực hiện chính sách của mình dựa trên dữ liệu đã đọc.

## 7. getAccessor không phải công cụ phân biệt tác giả với compiler

Accessor ngầm định cũng là method thật của lớp sau khi biên dịch. Accessor tường minh cũng được trả về qua cùng API `getAccessor()`.

Không có cờ `isExplicitAccessor()` trong `RecordComponent`. Cũng không dùng `Method.isSynthetic()` như một phép kiểm tra chắc chắn “ngầm định hay do tác giả viết”: các thành viên ngầm định được quy định bởi Java không nhất thiết là synthetic.

Trong ví dụ đầu, accessor tường minh có `synthetic=false`. Một accessor do compiler cung cấp cũng có thể có kết quả như vậy. Giá trị cờ này không chứng minh nguồn gốc tường minh của phần thân.

Nếu công cụ cần biết chính xác accessor có được viết trong tệp nguồn hay không, phải có thêm dữ liệu nguồn hoặc công cụ phân tích phù hợp. Không suy ra điều đó từ việc method có cùng tên với component, có annotation hay không, hoặc có vẻ chỉ trả một field.

Mục đích của `getAccessor()` là tìm đúng phương thức truy cập của component, không phải tái dựng lịch sử tác giả của method.

## 8. Ứng dụng trong công cụ đọc record

Một bộ đọc record có thể thực hiện theo thứ tự:

1. Kiểm tra `Class.isRecord()`.
2. Lấy `getRecordComponents()` để giữ cấu trúc và thứ tự component.
3. Với mỗi component, lấy `getAccessor()` và đọc metadata method cần thiết.
4. Giữ riêng metadata component, method và kiểu được chú thích.
5. Chỉ gọi accessor khi thực sự cần giá trị và khi đối tượng đầu vào phù hợp.

Không tìm accessor bằng cách lấy phần tử đầu tiên trong `getDeclaredMethods()` có cùng tên. Method overload hoặc bridge method có thể khiến một phép chọn đơn giản như vậy sai mục tiêu; thứ tự mảng metadata cũng không được dùng làm quy tắc chọn.

Khi gọi accessor tường minh:

- Nó có thể trả giá trị đã biến đổi, như ví dụ quan sát.
- Nó có thể ném ngoại lệ không kiểm tra dù không có `throws` trong khai báo.
- Ngoại lệ từ phần thân được `Method.invoke` bọc trong `InvocationTargetException`.
- Lời gọi vẫn chịu quy tắc truy cập của Reflection.

Nếu accessor thất bại, tự động chuyển sang đọc private field có thể làm thay đổi ngữ nghĩa của bộ đọc và bỏ qua logic công khai của record. Hãy xử lý lỗi theo hợp đồng của công cụ, thay vì âm thầm coi hai cách lấy giá trị là tương đương.

Một trình xem metadata chỉ cần tên, kiểu và annotation có thể dừng ở các bước đọc mô tả. Nó không cần chạy accessor để biết accessor nào thuộc component nào.

## 9. Các lỗi dễ gặp

| Giả định sai | Hệ quả |
| --- | --- |
| Accessor của record luôn là mã compiler sinh để đọc field | Bỏ qua phần thực hiện do tác giả viết |
| `getAccessor()` trả một method mặc định tách biệt với method tường minh | Hiểu sai method thực tế được dùng |
| Có cùng tên/kiểu nên field và accessor luôn trả cùng giá trị | Có thể đọc sai ngữ nghĩa dữ liệu |
| Annotation trên component luôn có trên accessor | Sai với accessor tường minh hoặc annotation không có target phù hợp |
| Không thấy annotation trên method nghĩa là component không có annotation | Bỏ sót metadata ở vị trí khác |
| Method không synthetic chắc chắn do tác giả viết | Phân loại sai accessor ngầm định |
| `equals` mặc định gọi accessor đã được tùy chỉnh | Bỏ qua giá trị field được dùng cho so sánh |
| Tùy chỉnh accessor không cần xét constructor/copy | Có thể làm mất quy tắc sao chép của record |

## 10. Tự kiểm tra

1. Khi record tự khai báo accessor, `RecordComponent.getAccessor()` trả method nào?
2. Vì sao một bộ đọc gọi accessor có thể nhận giá trị khác với một bộ đọc field?
3. `@Target(METHOD)` có đủ để bảo đảm annotation trên component được truyền sang một accessor tường minh không?
4. Nếu annotation còn trên component nhưng không có trên accessor, hai kết quả Reflection có mâu thuẫn không?
5. Có thể dùng `isSynthetic()` để xác định chắc chắn accessor được tác giả viết hay không?
6. Vì sao chuyển chuẩn hóa vào constructor giúp `NormalizedLabel` giữ quy tắc sao chép trong ví dụ?

Đáp án:

1. Method accessor thực tế đã được khai báo tường minh.
2. Accessor có phần thân thực thi riêng; đọc field lấy giá trị đang lưu.
3. Không. Accessor tường minh không tự nhận annotation truyền từ component; target chỉ là điều kiện về vị trí được phép dùng.
4. Không. Chúng mô tả hai phần tử được chú thích khác nhau.
5. Không; cần thêm dữ liệu nếu muốn xác định nguồn gốc phần thân.
6. Giá trị lưu đã được chuẩn hóa; accessor trả giá trị ấy và bản sao qua constructor giữ cùng giá trị.

## Tài liệu đối chiếu

- [JLS 17 — Thành viên record, accessor tường minh và annotation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3).
- [Java 17 — RecordComponent.getAccessor và metadata component](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html#getAccessor()).
- [Java 17 — Record và quy tắc sao chép](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).

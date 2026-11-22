# Điều kiện lưu giữ để đọc annotation bằng reflection

## Từ annotation trong mã nguồn đến dữ liệu lúc chạy

Một annotation có thể được dùng trong lúc biên dịch, được lưu trong tệp `.class` hoặc được giữ để chương trình đang chạy đọc lại. Vì vậy, nhìn thấy `@TênAnnotation` trong mã nguồn chưa đủ để kết luận `getAnnotation(...)` sẽ tìm được nó.

Reflection là cơ chế để chương trình khảo sát lớp, phương thức, trường và những thành phần khác khi đang chạy. Nếu một thành phần cần đọc annotation bằng reflection chuẩn của Java, kiểu annotation phải có chính sách lưu giữ `RetentionPolicy.RUNTIME` và annotation phải nằm trên đúng phần tử được truy vấn.

Bài này đối chiếu trực tiếp bốn trường hợp: `SOURCE`, không khai báo retention, `CLASS` và `RUNTIME`. Ví dụ dùng Java 17+ và không cần thư viện bên ngoài.

## Ba chính sách lưu giữ

| Chính sách | Sau khi biên dịch | Đọc bằng reflection chuẩn lúc chạy |
| --- | --- | --- |
| `SOURCE` | Lần sử dụng annotation bị trình biên dịch loại bỏ | Không |
| `CLASS` | Lần sử dụng annotation được ghi vào `.class` | Không qua API đọc annotation chuẩn |
| `RUNTIME` | Được ghi vào `.class` và giữ để JVM cung cấp khi chạy | Có, khi truy vấn đúng phần tử và đúng kiểu annotation |

Bảng áp dụng cho các vị trí khai báo có thể được phản chiếu như lớp và phương thức trong ví dụ. Bảng mô tả thời gian tồn tại của **mỗi lần sử dụng annotation**, không phải việc tệp `.class` định nghĩa kiểu annotation có được tạo hay không. Xem [`RetentionPolicy`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/RetentionPolicy.html).

Nếu không có `@Retention` trên khai báo kiểu annotation, chính sách mặc định là `CLASS`. Không có mặc định ngầm là `RUNTIME`. Muốn đọc lúc chạy, phải thể hiện quyết định đó tại khai báo `@interface`. Xem [`Retention`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Retention.html).

Ví dụ, `@Retention(RetentionPolicy.RUNTIME)` được đặt lên khai báo `RuntimeTag`; còn `@RuntimeTag("service")` được đặt lên lớp cần mô tả. Hai vị trí này có vai trò khác nhau.

## Ví dụ hoàn chỉnh: cùng một lớp, bốn retention

Lưu tệp `RetentionDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

public final class RetentionDemo {
    private RetentionDemo() {
    }

    @Retention(RetentionPolicy.SOURCE)
    @Target(ElementType.TYPE)
    @interface SourceTag {
    }

    @Target(ElementType.TYPE)
    @interface DefaultTag {
    }

    @Retention(RetentionPolicy.CLASS)
    @Target(ElementType.TYPE)
    @interface ClassTag {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface RuntimeTag {
        String value();
    }

    @SourceTag
    @DefaultTag
    @ClassTag
    @RuntimeTag("service")
    static class Subject {
        @RuntimeTag("operation")
        public void execute() {
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Class<Subject> type = Subject.class;
        System.out.println("SOURCE: "
                + (type.getDeclaredAnnotation(SourceTag.class) != null));
        System.out.println("DEFAULT(CLASS): "
                + (type.getDeclaredAnnotation(DefaultTag.class) != null));
        System.out.println("CLASS: "
                + (type.getDeclaredAnnotation(ClassTag.class) != null));

        RuntimeTag typeTag = type.getDeclaredAnnotation(RuntimeTag.class);
        System.out.println("RUNTIME: " + typeTag.value());

        Method method = type.getDeclaredMethod("execute");
        RuntimeTag methodTag = method.getDeclaredAnnotation(RuntimeTag.class);
        System.out.println("METHOD: " + methodTag.value());

        Retention retention = RuntimeTag.class.getAnnotation(Retention.class);
        System.out.println("POLICY: " + retention.value());
    }
}
```

Trong ví dụ cố định này, mã nguồn bảo đảm `RuntimeTag` có trên cả lớp và phương thức nên có thể gọi `value()` ngay. Với một bộ quét tổng quát, phải xử lý khả năng kết quả truy vấn là `null`.

Chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror RetentionDemo.java
java RetentionDemo
```

Stdout chính xác:

```text
SOURCE: false
DEFAULT(CLASS): false
CLASS: false
RUNTIME: service
METHOD: operation
POLICY: RUNTIME
```

### Đọc kết quả theo từng vị trí

`getDeclaredAnnotation(...)` trên `Subject.class` chỉ khảo sát annotation trực tiếp trên lớp `Subject`. Trong bốn annotation đó, chỉ `RuntimeTag` có chính sách cho phép đọc lúc chạy.

Phương thức `execute()` là một phần tử khác. Muốn lấy giá trị `"operation"`, mã phải tìm đối tượng `Method` của phương thức rồi truy vấn trên đối tượng đó. Truy vấn trên lớp không tự gom annotation của mọi phương thức bên trong.

Dòng `POLICY` lại khảo sát **kiểu annotation** `RuntimeTag.class` để lấy meta-annotation `Retention`. Việc `Retention` có thể được đọc trên khai báo này không biến `DefaultTag` thành annotation có retention `RUNTIME`; mỗi kiểu annotation có chính sách riêng.

Không in trực tiếp toàn bộ đối tượng annotation để làm kết quả chuẩn của bài. Đọc phần tử `value()` giúp kết quả rõ ràng và không phụ thuộc cách định dạng biểu diễn đối tượng của từng môi trường.

## Kiểm tra bytecode: có trong `.class` vẫn chưa đủ

Sau khi biên dịch ví dụ, chạy:

```shell
javap -v 'RetentionDemo$Subject'
```

Dấu nháy đơn giữ nguyên ký tự `$` trong tên lớp lồng khi dùng PowerShell hoặc shell hỗ trợ kiểu nháy này. Nếu dùng Windows Command Prompt, có thể dùng dấu nháy kép thay thế.

Trong kết quả, tìm các mục annotation của **lớp `Subject`**:

- `RuntimeInvisibleAnnotations` chứa `RetentionDemo$DefaultTag` và `RetentionDemo$ClassTag`.
- `RuntimeVisibleAnnotations` chứa `RetentionDemo$RuntimeTag` với giá trị `"service"`.
- Không có lần gắn `SourceTag` trong các mục annotation của lớp.

Phần chi tiết phương thức `execute()` cũng có annotation `RuntimeTag` với giá trị `"operation"`. Không cần nhớ số thứ tự trong constant pool hoặc toàn bộ đầu ra `javap`; chúng không phải hợp đồng đầu ra của bài.

Chỉ kết luận về các **mục annotation** tương ứng. Một tên lớp có thể xuất hiện ở nơi khác trong bytecode vì lý do khác; tìm chuỗi bất kỳ trên toàn bộ tệp không thay thế được việc đọc đúng thuộc tính.

`CLASS` phù hợp với công cụ phân tích bytecode cần metadata sau biên dịch. Công cụ như vậy không đồng nghĩa với `Class.getAnnotation()` hoặc `Method.getAnnotation()`. Không đổi sang `RUNTIME` chỉ vì metadata cần tồn tại trong tệp, nếu không có thành phần nào cần đọc nó qua reflection.

## Điều kiện lưu giữ là điều kiện cần, cần truy vấn đúng nữa

Với annotation khai báo như ví dụ, có thể kiểm tra theo trình tự:

1. **Đúng retention:** `@Retention(RUNTIME)` nằm trên đúng kiểu annotation.
2. **Đúng lần sử dụng:** annotation thực sự được gắn lên lớp hoặc thành viên cần khảo sát.
3. **Đúng đối tượng reflection:** dùng `Class`, `Method`, `Field`, `Parameter` hoặc thành phần phù hợp với nơi gắn annotation.
4. **Đúng kiểu annotation:** truyền đúng đối tượng `Class` của annotation cần tìm.
5. **Đúng bản đã biên dịch:** mã đang chạy phải dùng các tệp `.class` mới được tạo từ annotation và phần tử đã cập nhật.

Nếu chỉ thêm `RUNTIME` vào mã nguồn rồi chạy lại một tệp `.class` cũ, kết quả không thay đổi theo mong muốn. Hãy biên dịch lại kiểu annotation và các lớp sử dụng nó; với hệ thống đang chạy, cần nạp bản mới theo quy trình của ứng dụng.

Trong môi trường có nhiều bộ nạp lớp, hai kiểu có cùng tên đầy đủ vẫn có thể là hai kiểu khác nhau nếu do các class loader khác nhau định nghĩa. Khi trường hợp đơn giản đã đúng nhưng hệ thống lớn vẫn không tìm thấy, kiểm tra dependency và nguồn lớp được nạp thay vì chỉ so sánh tên dạng chuỗi.

## Chọn API đọc annotation phù hợp

| Nhu cầu | API thường dùng |
| --- | --- |
| Một annotation trực tiếp trên đúng phần tử | `getDeclaredAnnotation(MyTag.class)` |
| Một annotation có mặt theo quy tắc của API, có thể xét kế thừa từ lớp cha | `getAnnotation(MyTag.class)` |
| Kiểm tra có hay không theo cùng quy tắc với `getAnnotation` | `isAnnotationPresent(MyTag.class)` |
| Đọc nhiều lần lặp của annotation hỗ trợ `@Repeatable` | `getDeclaredAnnotationsByType(MyTag.class)` hoặc `getAnnotationsByType(MyTag.class)` |

`getAnnotation` không tự tìm annotation ở mọi nơi trong cây lớp. Việc xét annotation từ lớp cha còn phụ thuộc `@Inherited` và chỉ áp dụng trong phạm vi mà cơ chế đó quy định. Annotation trên phương thức cũng không tự trở thành annotation trên lớp. Xem [hợp đồng của `AnnotatedElement`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).

Một annotation lặp có thể được lưu thông qua annotation chứa; dùng API `...AnnotationsByType` khi cần đọc từng lần lặp. Tuy nhiên, bài hiện tại dùng annotation đơn, trực tiếp để tách riêng vấn đề retention.

Với mã quét tổng quát, dạng xử lý sau có thể đặt trong một phương thức khi đã có biến `type` và kiểu `RuntimeTag` như ví dụ:

```java
RuntimeTag tag = type.getDeclaredAnnotation(RuntimeTag.class);
if (tag != null) {
    System.out.println(tag.value());
}
```

`null` cho biết truy vấn đó không tìm thấy annotation theo quy tắc của API; nó không tự giải thích nguyên nhân là thiếu retention, sai phần tử hay sai bản lớp.

## Annotation khai báo và annotation trên kiểu sử dụng

`RUNTIME` cũng không làm mọi annotation xuất hiện qua cùng một lệnh. Annotation đặt trên **khai báo trường** và annotation đặt trên **kiểu của trường** là hai vị trí khác nhau.

Chẳng hạn, với một annotation chỉ có `@Target(TYPE_USE)` trên kiểu của trường, cần khảo sát `field.getAnnotatedType()` và đọc annotation từ `AnnotatedType`; chỉ gọi `field.getAnnotation(...)` không phải cách đọc vị trí kiểu đó. Xem [`AnnotatedType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedType.html).

Trong bài này, `RuntimeTag` chỉ có đích `TYPE` và `METHOD`, nên các lệnh trên lớp và phương thức là đúng vị trí. Khi mở rộng annotation sang vị trí khác, phải thiết kế cả `@Target` lẫn cách đọc tương ứng.

Annotation trên **khai báo biến cục bộ** hoặc **khai báo tham số của biểu thức lambda** không được giữ trong dạng nhị phân, kể cả khi kiểu annotation khai báo `CLASS` hay `RUNTIME`. Phân biệt chúng với annotation trên kiểu sử dụng tại những vị trí đó: annotation kiểu có quy tắc lưu giữ riêng, nhưng metadata trong thân phương thức không tự trở thành dữ liệu mà reflection chuẩn duyệt được. Xem [JLS về `Retention`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.2).

## Những điều retention không tự thực hiện

- `@Target` kiểm soát vị trí được phép đặt annotation; nó không quyết định thời gian lưu giữ.
- `@Documented` liên quan đến công bố annotation trong tài liệu; thêm nó không thay thế `@Retention(RUNTIME)`.
- `@Inherited` liên quan đến một số truy vấn qua lớp cha; nó không khôi phục metadata đã bị loại bỏ.
- `RUNTIME` không tự chạy phương thức, kiểm tra đầu vào hay cấu hình đối tượng. Phải có mã hoặc framework đọc annotation và thực hiện hành động.

Không thêm thao tác phá vỡ giới hạn truy cập như một cách thử ngẫu nhiên khi annotation trả về `null`. Đọc metadata và gọi phương thức riêng tư là hai nhu cầu khác nhau; trước tiên hãy kiểm tra retention, vị trí và API truy vấn.

## Thực hành kiểm chứng

1. Đổi `RuntimeTag` từ `RUNTIME` sang `CLASS`, biên dịch lại toàn bộ tệp. Các truy vấn lớp và phương thức với `RuntimeTag` sẽ trả `null`; cần kiểm tra trước khi gọi `value()` để tránh `NullPointerException`.
2. Khôi phục `RUNTIME`, bỏ `@RuntimeTag("service")` khỏi `Subject` nhưng giữ annotation trên `execute()`. Truy vấn lớp trả `null`, còn truy vấn phương thức vẫn đọc được `"operation"`.
3. Khôi phục ví dụ, thêm `@Retention(RUNTIME)` vào `DefaultTag`. Sau khi biên dịch lại, dòng `DEFAULT(CLASS)` sẽ in `true`; đổi nhãn dòng in cho phù hợp với chính sách mới khi tự thử.
4. Đối chiếu phần annotation của `Subject` trong `javap -v` trước và sau mỗi thay đổi, để nối được bằng chứng từ mã nguồn, `.class` và reflection.

Người học cần giải thích được ba kết quả khác nhau: metadata bị loại khỏi lần sử dụng sau biên dịch, metadata còn trong `.class` nhưng không được reflection chuẩn đọc, và metadata được đọc khi chạy trên đúng phần tử.
# @Retention với SOURCE, CLASS và RUNTIME

## 1. Retention trả lời câu hỏi annotation được giữ tới đâu

Annotation gắn siêu dữ liệu vào mã Java. Sau khi trình biên dịch xử lý mã nguồn và tạo tệp `.class`, không phải annotation nào cũng còn có thể được đọc theo cùng một cách.

Meta-annotation `@Retention` được đặt trên khai báo một kiểu annotation để chỉ định chính sách lưu giữ những lần sử dụng annotation đó:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Feature {
    String value();
}
```

Khi viết `@Feature("search")` trên một lớp, chính sách RUNTIME cho phép annotation đó được giữ để đọc qua reflection lúc chạy.

Điểm cần tách rõ:

- `@Retention` đặt trên **kiểu annotation**.
- Chính sách đó điều khiển cách giữ **những lần dùng annotation** trên các phần tử chương trình.
- Chính sách lưu giữ không tự chạy một hành vi nghiệp vụ, không tự gọi framework và không thay thế đoạn mã đọc annotation.

Đây là cơ chế vẫn dùng trong Java hiện đại. Các ví dụ trong bài chạy được trên Java 17+.

## 2. So sánh ba chính sách

| Chính sách | Khi xử lý mã nguồn | Metadata của lần dùng được ghi vào class file | Đọc lần dùng qua reflection thông thường lúc chạy |
| --- | --- | --- | --- |
| SOURCE | Có thể được trình biên dịch/công cụ xử lý | Không | Không |
| CLASS | Có thể được xử lý | Có | Không |
| RUNTIME | Có thể được xử lý | Có | Có, qua API phù hợp |

Bảng mô tả trường hợp annotation trên khai báo kiểu như các ví dụ trong bài. Một số vị trí có quy tắc lưu giữ riêng, được lưu ý ở phần cuối.

Thứ tự SOURCE → CLASS → RUNTIME là cách hình dung phạm vi lưu giữ tăng dần. Nó không có nghĩa annotation thuộc chính sách sau thì không thể được đọc ở giai đoạn trước. Chẳng hạn annotation có RUNTIME vẫn có thể được công cụ đọc khi biên dịch.

### SOURCE: chỉ cần thông tin trong quá trình xử lý nguồn

Những lần dùng annotation SOURCE bị loại khỏi metadata của class file. Ví dụ quen thuộc là `@Override` và `@SuppressWarnings`: trình biên dịch dùng chúng để kiểm tra hoặc điều chỉnh cảnh báo, không cần phản chiếu lại chúng từ lớp đã biên dịch.

Nếu tự định nghĩa annotation SOURCE, nó không tự có công dụng kiểm tra như `@Override`. Muốn nó có ý nghĩa riêng, cần trình xử lý/công cụ hiểu annotation đó.

SOURCE không có nghĩa “không sinh mã”. Một công cụ xử lý annotation có thể dùng dữ liệu từ nguồn để sinh mã khác; mã được sinh có thể tồn tại lúc chạy dù annotation nguồn không còn được lưu.

### CLASS: giữ metadata trong tệp nhị phân

Lần dùng annotation CLASS được ghi trong class file, để công cụ đọc bytecode hoặc công cụ phân tích nhị phân có thể sử dụng.

Reflection thông thường như `Class.getAnnotation(...)` không cung cấp annotation có chính sách CLASS. Vì vậy, kết quả null từ reflection không đủ để kết luận annotation đã biến mất khỏi tệp `.class`.

Tên CLASS cũng không nói rằng annotation chỉ dùng được trên lớp; vị trí áp dụng do `@Target` quy định.

### RUNTIME: cho phép đọc metadata lúc chạy

Lần dùng annotation RUNTIME được lưu trong class file và có thể được truy cập qua cơ chế reflection thích hợp.

Ví dụ, một framework có thể đọc annotation trên lớp hoặc phương thức để quyết định cách cấu hình. Công việc đó do framework thực hiện; RUNTIME không tự tạo cơ chế quét lớp, không gọi phương thức và không tự đăng ký đối tượng.

Không phải mọi framework đều bắt buộc dùng RUNTIME cho mọi annotation. Một công cụ xây chỉ mục hoặc đọc bytecode có thể có cách tiêu thụ annotation CLASS. Phải dựa vào cơ chế đọc thực tế của bên sử dụng.

## 3. Nếu không khai báo @Retention thì mặc định là CLASS

Ví dụ:

```java
@interface DefaultMark {
}
```

Những lần sử dụng `DefaultMark` có chính sách mặc định CLASS. Chúng không mặc định trở thành annotation runtime chỉ vì kiểu annotation có thể được nạp hoặc vì tên kết thúc bằng `Mark`.

Đây là một nguyên nhân thường gặp khi tự viết annotation rồi thấy:

```java
SomeType.class.getAnnotation(DefaultMark.class)
```

trả về null. Nếu nhu cầu là đọc bằng reflection lúc chạy, cần khai báo RUNTIME và biên dịch lại các lớp có sử dụng annotation.

Không nên hiểu mặc định CLASS là có một dòng `@Retention(CLASS)` được tự chèn vào mã nguồn. Đó là chính sách hiệu lực khi thiếu meta-annotation tường minh.

## 4. Ví dụ đầy đủ: cùng một lớp, bốn chính sách

Lưu thành `RetentionDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

public class RetentionDemo {
    @Retention(RetentionPolicy.SOURCE)
    @Target(ElementType.TYPE)
    @interface SourceMark {
    }

    @Retention(RetentionPolicy.CLASS)
    @Target(ElementType.TYPE)
    @interface BinaryMark {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface RuntimeMark {
        String value();
    }

    @Target(ElementType.TYPE)
    @interface DefaultMark {
    }

    @SourceMark
    @BinaryMark
    @RuntimeMark("enabled")
    @DefaultMark
    static class Example {
    }

    public static void main(String[] args) {
        Class<Example> type = Example.class;

        System.out.println("SOURCE="
                + type.isAnnotationPresent(SourceMark.class));
        System.out.println("CLASS="
                + type.isAnnotationPresent(BinaryMark.class));
        System.out.println("RUNTIME="
                + type.isAnnotationPresent(RuntimeMark.class));
        System.out.println("DEFAULT="
                + type.isAnnotationPresent(DefaultMark.class));

        RuntimeMark mark = type.getAnnotation(RuntimeMark.class);
        System.out.println("runtime value=" + mark.value());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 RetentionDemo.java
java RetentionDemo
```

Kết quả:

```text
SOURCE=false
CLASS=false
RUNTIME=true
DEFAULT=false
runtime value=enabled
```

`isAnnotationPresent` kiểm tra khả năng quan sát annotation theo mô hình reflection. Các dòng false cho CLASS và DEFAULT không chứng minh hai lần dùng đó không được ghi trong class file.

Biến `mark` khác null vì `Example` được gắn trực tiếp `RuntimeMark` có RUNTIME. Trong mã tổng quát không biết trước annotation có hiện diện hay không, cần xử lý trường hợp `getAnnotation` trả về null.

Một chi tiết quan trọng: chương trình vẫn tham chiếu được tới `SourceMark.class`. SOURCE loại metadata của **lần dùng** `@SourceMark` trên `Example`; nó không cấm trình biên dịch sinh class file cho chính kiểu annotation `SourceMark`.

## 5. Kiểm tra class file để phân biệt SOURCE với CLASS

Sau khi biên dịch, dùng công cụ đi kèm JDK:

```shell
javap -v -p 'RetentionDemo$Example'
```

Cách đặt tên lớp trong dấu nháy đơn phù hợp với PowerShell và các shell phổ biến hỗ trợ dấu nháy đơn; nếu dùng một shell khác, cần giữ nguyên ký tự `$` trong tên lớp lồng.

Trong kết quả, quan sát các mục metadata annotation:

- `RuntimeVisibleAnnotations` chứa lần dùng `RetentionDemo$RuntimeMark` và giá trị `"enabled"`.
- `RuntimeInvisibleAnnotations` chứa lần dùng `RetentionDemo$BinaryMark` và `RetentionDemo$DefaultMark`.
- Không có lần dùng `RetentionDemo$SourceMark` trên `Example`.

Ở đây, “Invisible” nghĩa là không được cung cấp qua reflection runtime thông thường. Metadata vẫn có trong class file và công cụ phân tích class file vẫn đọc được nó.

Không nên chỉ tìm chuỗi tên annotation trong mọi tệp `.class` để kết luận retention. Tệp của chính kiểu annotation, tham chiếu trong phương thức kiểm tra hoặc dữ liệu khác có thể chứa tên đó. Cần xem đúng class file và đúng thuộc tính annotation của phần tử được gắn annotation.

Bytecode của ví dụ giúp phân biệt:

1. SOURCE không lưu lần dùng trong class file đích.
2. CLASS có lưu lần dùng nhưng reflection không thấy.
3. RUNTIME có lưu lần dùng và reflection đọc được.

## 6. Chọn retention theo bên tiêu thụ metadata

### Chọn SOURCE khi nhu cầu kết thúc ở xử lý nguồn

Phù hợp khi annotation phục vụ kiểm tra nguồn hoặc sinh mã và các bên dùng class file sau đó không cần đọc lại annotation gốc.

Cần kiểm tra vòng đời công cụ. Nếu một công cụ ở bước sau chỉ có class file và không có nguồn, annotation SOURCE không còn là dữ liệu đầu vào cho bước đó.

### Chọn CLASS khi công cụ cần đọc dữ liệu từ class file

Phù hợp khi có công cụ quét bytecode, tạo chỉ mục hoặc phân tích nhị phân được thiết kế để đọc annotation đó mà không cần reflection trên các lớp đã nạp.

CLASS là một lựa chọn có ý nghĩa riêng; không phải một trạng thái “annotation chưa cấu hình xong”. Nhưng nếu bên tiêu thụ chỉ dùng `getAnnotation`, CLASS không đáp ứng nhu cầu đó.

### Chọn RUNTIME khi metadata phải có sẵn cho reflection

Phù hợp khi ứng dụng hoặc framework thực sự đọc annotation lúc chạy qua reflection.

Không cần chọn RUNTIME cho mọi annotation theo thói quen. Việc giữ thêm metadata không thay thế thiết kế rõ ràng về nơi đặt annotation, cách đọc, thời điểm đọc và ý nghĩa của các phần tử.

Nếu đổi annotation từ CLASS/SOURCE sang RUNTIME, phải biên dịch lại các lớp sử dụng để class file của chúng có đúng metadata. Chỉ thay tệp chứa định nghĩa annotation không thể làm xuất hiện hồi tố lần dùng đã bị loại khỏi một class file cũ.

## 7. Retention độc lập với các quy tắc nào?

### @Target: được đặt ở đâu

`@Target` xác định vị trí được phép dùng annotation, ví dụ TYPE hoặc METHOD. Nó không quyết định annotation có được giữ tới runtime.

`@Retention` quyết định lưu giữ, không cho phép bỏ qua lỗi đặt annotation sai vị trí. Trong ví dụ, cả ba kiểu SourceMark, BinaryMark, RuntimeMark đều có cùng target TYPE nhưng retention khác nhau.

### @Inherited: tra cứu qua lớp cha

RUNTIME không tự làm annotation trên lớp cha trở thành annotation được kế thừa khi tra cứu lớp con. Đó là một quy tắc riêng liên quan tới `@Inherited` và cách dùng API tra cứu.

Không nên xem kết quả null ở lớp con là bằng chứng retention sai mà chưa kiểm tra nơi annotation được đặt và chính sách kế thừa.

### Annotation processing: ai đọc trong quá trình biên dịch

Retention không tự bật một bộ xử lý annotation. Một annotation tự định nghĩa vẫn cần bộ xử lý được cấu hình nếu muốn kiểm tra hoặc sinh mã.

Bộ xử lý làm việc với mô hình phần tử trong quá trình biên dịch; annotation có RUNTIME không vì thế bị loại khỏi khả năng xử lý ở giai đoạn này. Retention quy định lưu giữ, không phải danh sách duy nhất các giai đoạn công cụ được phép đọc dữ liệu.

## 8. Ngoại lệ vị trí cần biết

Bảng đầu bài áp dụng trực tiếp cho ví dụ gắn annotation trên khai báo kiểu. Không nên suy rộng rằng mọi lần dùng có RUNTIME ở bất kỳ vị trí nào cũng có thể lấy bằng `Class.getAnnotation`.

- Annotation trên phương thức phải được đọc từ đối tượng `Method` tương ứng; tương tự với trường và tham số.
- Annotation trên khai báo biến cục bộ hoặc khai báo tham số của biểu thức lambda không được giữ trong biểu diễn nhị phân chỉ nhờ đặt RUNTIME.
- Annotation đặt trên một lần dùng kiểu (type-use annotation) có cơ chế lưu giữ và API đọc riêng, chẳng hạn các API thuộc mô hình `AnnotatedType` tại những vị trí phản chiếu được. Nó không tự trở thành annotation trên khai báo lớp.
- Không phải mọi vị trí có dữ liệu type-use trong class file đều có một đối tượng reflection trực tiếp cho từng biểu thức trong thân phương thức.

Vì vậy, khi không đọc được annotation, cần kiểm tra cả **retention**, **vị trí gắn** và **API đang dùng để đọc**.

## 9. Quy trình kiểm tra khi reflection trả về null

1. Annotation có được gắn trực tiếp ở phần tử đang đọc không?
2. Kiểu annotation đã có `@Retention(RUNTIME)` chưa?
3. Đã biên dịch lại lớp sử dụng annotation sau khi đổi chính sách chưa?
4. Đang đọc đúng lớp/phương thức/trường hoặc mô hình type-use chưa?
5. Nếu tra cứu trên lớp con, có đang nhầm retention với kế thừa annotation không?
6. Nếu mục tiêu là đọc từ class file, đã dùng công cụ đọc bytecode thay vì chỉ dùng reflection chưa?

Thực hành: đổi `BinaryMark` trong ví dụ thành RUNTIME, biên dịch lại rồi chạy. Dòng `CLASS=` sẽ trở thành true vì nó đang kiểm tra tên kiểu `BinaryMark`, còn chính sách thực của kiểu đó đã đổi. Sau đó xem lại `javap` để thấy lần dùng chuyển từ nhóm invisible sang visible.

## Tài liệu đối chiếu

- [RetentionPolicy — Ý nghĩa SOURCE, CLASS, RUNTIME](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/RetentionPolicy.html).
- [Retention — Chính sách mặc định CLASS](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Retention.html).
- [JLS §9.6.4.2 — Quy tắc retention](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.2).
- [JVMS §4.7.17 — RuntimeInvisibleAnnotations](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.17).

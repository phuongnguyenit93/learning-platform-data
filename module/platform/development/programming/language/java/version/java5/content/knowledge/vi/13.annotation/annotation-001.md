# Annotation và vai trò của siêu dữ liệu trong chương trình

Một chương trình không chỉ cần mã thực hiện công việc. Công cụ biên dịch, công cụ kiểm tra và thư viện còn có thể cần thông tin mô tả ý định của mã: một phương thức có chủ đích ghi đè phương thức cha hay không, một kiểu được dùng cho vai trò gì, hoặc một khai báo có nhãn cấu hình nào.

**Annotation là cách gắn siêu dữ liệu (metadata) có cấu trúc vào mã Java.** Siêu dữ liệu là thông tin mô tả một thành phần khác của chương trình. Nó không phải thân phương thức thực hiện nghiệp vụ.

Điểm cần nhớ ngay từ đầu: để hiểu tác dụng của một annotation, cần biết **nó mô tả điều gì, ai đọc nó và khi nào thông tin đó được đọc**.

## 1. Phân biệt phần thực hiện và phần mô tả

Xét một phương thức của lớp triển khai `Runnable`:

```java
@Override
public void run() {
    System.out.println("export report");
}
```

Đây là đoạn minh họa đặt trong một lớp phù hợp:

- Thân `run` là mã thực hiện: in một dòng khi phương thức được gọi.
- `@Override` mô tả ý định rằng phương thức ghi đè hoặc triển khai một phương thức của kiểu cha theo các điều kiện Java quy định.
- Trình biên dịch đọc `@Override` và kiểm tra ý định đó.

Nếu một phương thức thật sự đáp ứng quy tắc ghi đè, bỏ `@Override` không tự làm nó ngừng ghi đè. Annotation giúp trình biên dịch phát hiện trường hợp người viết tưởng mình đang ghi đè nhưng chữ ký không phù hợp.

Do đó, không nên hiểu annotation như “một lệnh bí mật nằm trước phương thức”. Nó là dữ liệu đầu vào cho một cơ chế xử lý.

## 2. Những thành phần trong mô hình annotation

| Thành phần | Vai trò |
| --- | --- |
| Kiểu annotation | Định nghĩa tên annotation, các phần tử dữ liệu và điều kiện sử dụng |
| Cách dùng annotation | Gắn dữ liệu cụ thể vào một vị trí của chương trình |
| Phần tử được chú thích | Lớp, phương thức, trường, tham số hoặc vị trí khác được cho phép |
| Bên xử lý annotation | Trình biên dịch, annotation processor, công cụ phân tích hoặc mã thư viện/ứng dụng |
| Chính sách lưu giữ | Quy định thông tin annotation còn tồn tại đến giai đoạn nào |

Ví dụ, `@TaskLabel("export")` gồm tên kiểu annotation `TaskLabel` và giá trị dữ liệu `"export"`. Lớp được gắn annotation là đối tượng được mô tả; mã đọc annotation quyết định sẽ làm gì với nhãn đó.

Các tên tiếng Anh thường gặp:

- **Annotation interface:** kiểu annotation được khai báo bằng `@interface`.
- **Element:** phần tử dữ liệu trong kiểu annotation, chẳng hạn `String value();`.
- **Meta-annotation:** annotation dùng để mô tả chính một kiểu annotation, như `@Target` và `@Retention`.
- **Reflection:** cơ chế kiểm tra cấu trúc và một số siêu dữ liệu của chương trình trong lúc chạy.

Các khái niệm này liên quan với nhau nhưng không đồng nghĩa. Đặc biệt, annotation không bắt buộc phải được đọc bằng reflection; nhiều annotation chỉ phục vụ biên dịch hoặc công cụ xây dựng.

## 3. Vì sao dùng metadata có cấu trúc?

### Thể hiện ý định để công cụ kiểm tra

Với `@Override`, trình biên dịch có thể đối chiếu ý định với khai báo thực tế. Một dòng comment như `// overrides parent` không tạo ra nghĩa vụ kiểm tra tương đương.

### Tách mô tả khỏi mã thực hiện lặp lại

Nếu nhiều lớp đều cần một nhãn cho công cụ quan sát hoặc đăng ký, có thể gắn nhãn gần khai báo lớp rồi để một thành phần chung đọc. Người viết không cần lặp cùng một đoạn truy vấn cấu hình trong từng lớp.

### Cung cấp đầu vào cho công cụ

Annotation processor có thể dùng metadata trong quá trình biên dịch để kiểm tra quy tắc hoặc tạo tệp mã/tài nguyên. Thư viện cũng có thể dùng annotation lúc chạy để xây dựng hành vi theo quy ước riêng.

Lợi ích phụ thuộc vào bên xử lý. Chỉ định nghĩa hoặc gắn một annotation mới không tự tạo bộ sinh mã, bộ kiểm thử hay cơ chế đăng ký.

## 4. Ai đọc annotation, vào lúc nào?

| Giai đoạn | Bên xử lý điển hình | Tác dụng có thể có |
| --- | --- | --- |
| Biên dịch | Trình biên dịch Java | Kiểm tra các annotation có ngữ nghĩa được quy định, ví dụ `@Override` |
| Xử lý annotation khi xây dựng | Annotation processor được cấu hình | Kiểm tra mô hình, phát thông báo hoặc tạo tệp |
| Phân tích tệp class | Công cụ đọc bytecode | Đọc metadata được lưu trong tệp `.class` |
| Chạy chương trình | Thư viện/ứng dụng, có thể qua reflection | Đọc metadata và thực hiện quy tắc của thư viện/ứng dụng |

Không phải mọi bên xử lý đều nhìn thấy mọi annotation.

Ba chính sách `RetentionPolicy` cơ bản:

- `SOURCE`: annotation được trình biên dịch loại bỏ khỏi đầu ra class.
- `CLASS`: annotation được ghi vào tệp class nhưng không được giữ để đọc qua reflection theo cách thông thường lúc chạy.
- `RUNTIME`: annotation được ghi vào class và giữ lại để có thể đọc bằng reflection lúc chạy.

Nếu không khai báo `@Retention`, mặc định là `CLASS`, không phải `RUNTIME`.

Chính sách lưu giữ và việc có bên xử lý là hai vấn đề khác nhau. Đặt `RUNTIME` chỉ làm metadata có thể được đọc khi chạy; nó không tự tạo một vòng quét hoặc tự gọi một phương thức.

`@Override` có chính sách `SOURCE` và vẫn hữu ích: vai trò của nó nằm ở kiểm tra khi biên dịch, không phải ở khả năng truy vấn lúc chạy.

## 5. Ví dụ hoàn chỉnh: metadata chỉ có tác dụng khi được đọc

Ví dụ sau dùng duy nhất JDK, chạy trên Java 17+. Nó có:

1. Một kiểu annotation `TaskLabel`.
2. Một lớp công việc có nhãn và một lớp công việc không có nhãn.
3. Một phương thức xử lý đọc nhãn rồi in thông tin trước khi chạy công việc.

Lưu thành `AnnotationMetadataDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

public class AnnotationMetadataDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface TaskLabel {
        String value();
    }

    @TaskLabel("export")
    static final class ExportTask implements Runnable {
        @Override
        public void run() {
            System.out.println("work: export");
        }
    }

    static final class CleanupTask implements Runnable {
        @Override
        public void run() {
            System.out.println("work: cleanup");
        }
    }

    static void runWithMetadata(Runnable task) {
        TaskLabel info = task.getClass().getAnnotation(TaskLabel.class);
        String label = info == null ? "unlabeled" : info.value();
        System.out.println("label: " + label);
        task.run();
    }

    public static void main(String[] args) {
        ExportTask export = new ExportTask();

        System.out.println("direct:");
        export.run();

        System.out.println("through consumer:");
        runWithMetadata(export);

        System.out.println("unannotated:");
        runWithMetadata(new CleanupTask());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 AnnotationMetadataDemo.java
java AnnotationMetadataDemo
```

Stdout:

```text
direct:
work: export
through consumer:
label: export
work: export
unannotated:
label: unlabeled
work: cleanup
```

### Đọc bằng chứng từ kết quả

Lời gọi trực tiếp `export.run()` chỉ in `work: export`. Việc lớp có `@TaskLabel` không tự chèn thêm thao tác in nhãn vào thân phương thức.

Khi gọi `runWithMetadata(export)`, mã ứng dụng chủ động đọc `TaskLabel`, lấy giá trị rồi in `label: export`. Dòng bổ sung đến từ mã xử lý metadata.

Với `CleanupTask`, truy vấn không tìm được `TaskLabel`; phương thức xử lý chọn giá trị dự phòng `unlabeled`. Chương trình đã có một quyết định rõ ràng cho trường hợp thiếu metadata.

Nếu đổi `@TaskLabel("export")` thành `@TaskLabel("reports")`, bên đọc sẽ in nhãn mới. Nội dung `work: export` trong thân `run` vẫn giữ nguyên vì nó do mã thực hiện quyết định.

## 6. Các phần của annotation trong ví dụ

### Khai báo kiểu bằng @interface

```java
public @interface TaskLabel {
    String value();
}
```

Đoạn này định nghĩa một kiểu annotation có phần tử dữ liệu `value` mang kiểu `String`. Nó không định nghĩa thân xử lý để chạy mỗi khi ai đó dùng `@TaskLabel`.

Cú pháp `@TaskLabel("export")` là cách viết ngắn khi cung cấp phần tử mang tên `value`; cách viết tường minh là `@TaskLabel(value = "export")`.

### Target quy định vị trí sử dụng

```java
@Target(ElementType.TYPE)
```

Trong ví dụ, annotation được thiết kế để gắn vào khai báo kiểu như lớp. Nếu đem `@TaskLabel` gắn vào một phương thức, trình biên dịch sẽ từ chối vì vị trí đó không nằm trong target đã khai báo.

Vị trí gắn annotation và vị trí mà bên xử lý truy vấn phải khớp với nhau. Đọc annotation trên lớp không tự đồng nghĩa với đọc annotation trên từng phương thức của lớp.

### Retention quy định khả năng đọc lúc chạy

```java
@Retention(RetentionPolicy.RUNTIME)
```

Mã `getAnnotation(TaskLabel.class)` trong ví dụ cần annotation có thể được quan sát bằng reflection khi chạy. Chuyển retention sang `CLASS` rồi biên dịch lại sẽ làm nhãn không còn được truy vấn theo cách này; bên xử lý sẽ đi vào nhánh dự phòng.

### Mã xử lý quyết định ý nghĩa nghiệp vụ

Trong bài, ý nghĩa của `TaskLabel` chỉ là nhãn được in trước công việc. Không có quy tắc Java mặc định nào nói annotation này phải lập lịch chạy, lưu dữ liệu hoặc cấp quyền thực hiện công việc.

Nếu cần các hành vi đó, phải có triển khai và hợp đồng cụ thể. Khi dùng annotation của một thư viện, cần đọc cả tài liệu bên xử lý, không chỉ nhìn tên annotation.

## 7. Phân biệt với comment, modifier và cấu hình

| Cơ chế | Ví dụ | Khác biệt chính |
| --- | --- | --- |
| Comment | `// task label: export` | Văn bản cho người đọc; không tự có mô hình annotation để công cụ truy vấn |
| Annotation | `@TaskLabel("export")` | Metadata theo kiểu có cấu trúc và quy tắc sử dụng |
| Modifier | `public`, `final`, `static` | Thành phần ngôn ngữ có quy tắc trực tiếp về khai báo và hành vi liên quan |
| Dữ liệu cấu hình lúc chạy | Tham số dòng lệnh, tệp cấu hình | Có thể thay đổi theo môi trường mà không cần sửa vị trí gắn annotation |

Annotation không thay thế mọi dạng cấu hình. Nếu một giá trị cần thay đổi theo môi trường triển khai, đặt giá trị đó cố định trong mã annotation có thể không phù hợp.

Ngược lại, thông tin ổn định gắn với một khai báo có thể dễ đọc hơn khi đặt ngay gần khai báo đó.

## 8. Lỗi hiểu phổ biến

- **Cho rằng tất cả annotation đều có hiệu lực lúc chạy:** một số chỉ phục vụ biên dịch, số khác có retention khác nhau.
- **Cho rằng đặt RUNTIME là đủ:** còn phải có mã hoặc công cụ đọc và xử lý annotation.
- **Quên bên xử lý cần được cấu hình:** một annotation processor phải thực sự khả dụng và được bật theo công cụ xây dựng đang dùng.
- **Truy vấn nhầm vị trí:** annotation trên lớp không tự là annotation trên phương thức.
- **Đồng nhất annotation với hành vi được bảo đảm:** một nhãn tự tạo không thực thi kiểm tra nghiệp vụ nếu không có mã xử lý.
- **Dùng annotation cho dữ liệu thay đổi liên tục:** trạng thái đối tượng lúc chạy thường cần mô hình dữ liệu thông thường.

Khi đọc một annotation lạ, hãy tìm kiểu khai báo, target, retention và thành phần sử dụng nó. Bốn thông tin ấy thường giải thích được phần lớn “điều gì đang xảy ra” mà không cần giả định cơ chế đặc biệt.

## 9. Thực hành ngắn

1. Đổi nhãn `export` thành `reports`, biên dịch lại và dự đoán dòng nào đổi.
2. Bỏ `@TaskLabel` khỏi `ExportTask`, giữ nguyên phần xử lý.
3. Đổi retention sang `CLASS`, biên dịch lại và quan sát nhãn.
4. Thử gắn `@TaskLabel` lên phương thức `run` khi target vẫn chỉ là `TYPE`.

Kết quả mong đợi:

1. Nhãn do `runWithMetadata` in đổi thành `reports`; thân `run` vẫn in `work: export`.
2. Lời gọi qua bên xử lý in nhãn `unlabeled`.
3. Bên xử lý qua reflection không nhận được annotation này và dùng nhãn dự phòng.
4. Lỗi biên dịch do vị trí gắn không hợp lệ.

Mỗi thí nghiệm nên bắt đầu từ bản chương trình gốc để quan sát một thay đổi riêng.

## Tài liệu đối chiếu

Xem [JLS 21 §9.7 — Annotations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7), [Override](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Override.html), [RetentionPolicy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/RetentionPolicy.html), [Retention](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Retention.html) và API [javax.annotation.processing](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/package-summary.html).

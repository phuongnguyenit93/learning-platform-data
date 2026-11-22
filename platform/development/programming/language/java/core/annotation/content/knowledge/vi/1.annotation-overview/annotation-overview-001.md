# Chú thích (annotation) trong Java và vai trò của siêu dữ liệu

## 1. Annotation là gì?

**Annotation (chú thích)** là cách gắn **siêu dữ liệu (metadata)** vào một thành phần của chương trình Java bằng cú pháp bắt đầu với dấu `@`. Thành phần được gắn có thể là lớp, phương thức, trường, tham số, constructor hoặc những vị trí khác mà loại annotation cho phép.

**Siêu dữ liệu** nghĩa là “dữ liệu mô tả dữ liệu”. Trong mã Java, annotation mô tả thêm thông tin về một thành phần: *thành phần đó có ý nghĩa gì, cần được kiểm tra ra sao, hoặc công cụ/framework nên xử lý nó thế nào*. Ví dụ:

```java
class Task {
    @Override
    public String toString() {
        return "Task";
    }
}
```

`@Override` cho trình biên dịch biết rằng `toString()` được định nghĩa để ghi đè một phương thức ở kiểu cha. Nếu lập trình viên viết sai chữ ký đến mức phương thức không thực sự ghi đè, trình biên dịch sẽ báo lỗi. Annotation ở đây giúp phát hiện lỗi; nó không tự làm thay đổi logic trả về `"Task"`.

Khác với chú thích bằng `//` hoặc `/* ... */` dành chủ yếu cho người đọc, annotation có cấu trúc được Java nhận biết, nên compiler, công cụ build, thư viện hoặc framework có thể kiểm tra và xử lý theo quy tắc xác định.

## 2. Vai trò của annotation: mô tả để một bên khác xử lý

Một annotation tự nó **không phải câu lệnh thực thi nghiệp vụ**. Việc đặt `@Something` trên một phương thức không khiến phương thức đó tự chạy. Tác dụng chỉ xuất hiện khi **một cơ chế hiểu annotation đó** đọc và xử lý nó.

| Ai xử lý? | Thời điểm | Ví dụ | Tác dụng |
| --- | --- | --- | --- |
| Trình biên dịch Java | Khi biên dịch | `@Override` | Kiểm tra phương thức có thực sự override hay không. |
| Trình biên dịch Java | Khi biên dịch | `@SuppressWarnings("unchecked")` | Yêu cầu compiler bỏ qua nhóm cảnh báo đã chỉ định tại phạm vi phù hợp; không sửa nguyên nhân của cảnh báo. |
| Annotation processor | Trong quá trình biên dịch | Annotation do thư viện/công cụ định nghĩa | Có thể kiểm tra quy tắc, phát thông báo lỗi hoặc sinh thêm mã/tài nguyên. |
| Framework/thư viện | Khi khởi động hoặc trong lúc chạy | `@Test` của JUnit, `@Transactional` của Spring | Framework tìm annotation và áp dụng cơ chế do **chính framework** triển khai. |
| Mã dùng Reflection | Khi chạy, nếu annotation được giữ đến runtime | Annotation tự định nghĩa có `@Retention(RUNTIME)` | Chương trình đọc metadata rồi quyết định xử lý tiếp. |

Ví dụ, với Spring, việc một phương thức có `@Transactional` không có nghĩa JVM tự mở transaction. Spring phải quản lý đối tượng và áp dụng cơ chế transaction tương ứng; hành vi cụ thể còn phụ thuộc cách phương thức được gọi và cấu hình Spring.

Nhờ đó, annotation tách được **thông tin khai báo** khỏi **mã thực thi cơ chế**: lập trình viên đánh dấu ý định ngay gần thành phần liên quan, còn công cụ xử lý tập trung theo quy tắc riêng.

## 3. Cú pháp và dữ liệu bên trong annotation

Cú pháp thường gặp:

- Không truyền phần tử: `@Override`, `@Deprecated`.
- Truyền phần tử có tên: `@SuppressWarnings(value = "unchecked")`.
- Viết ngắn khi chỉ gán phần tử tên `value`: `@SuppressWarnings("unchecked")`.
- Truyền nhiều phần tử: `@Info(author = "Lan", version = 2)` (với `@Info` được định nghĩa như ví dụ bên dưới).

Các giá trị trong annotation có tính **khai báo, cố định tại lúc biên dịch**. Loại phần tử được phép gồm kiểu nguyên thủy, `String`, `Class`, enum, loại annotation khác và mảng một chiều của các loại đó. Không thể dùng một đối tượng tùy ý, giá trị lấy từ request đang chạy hay biến cục bộ thay đổi ở runtime làm giá trị phần tử.

Java cung cấp sẵn một số annotation như `@Override`, `@Deprecated`, `@SuppressWarnings`. Ta cũng có thể định nghĩa annotation riêng bằng từ khóa `@interface`. Loại annotation tự định nghĩa thường có các **phần tử** trông giống khai báo phương thức không tham số và có thể có giá trị mặc định.

## 4. Ví dụ hoàn chỉnh: tự định nghĩa, gắn và đọc annotation

Tạo tệp **`AnnotationDemo.java`** với nội dung sau. Ví dụ dùng Java 17+ và chỉ cần JDK, không cần Spring hay thư viện ngoài.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Info {
    String author();
    int version() default 1;
}

public class AnnotationDemo {
    @Info(author = "Lan", version = 2)
    public void process() {
        System.out.println("Đang xử lý");
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Info info = AnnotationDemo.class
                .getDeclaredMethod("process")
                .getAnnotation(Info.class);

        System.out.println(info.author());
        System.out.println(info.version());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 AnnotationDemo.java
java AnnotationDemo
```

Kết quả chuẩn (stdout):

```text
Lan
2
```

Giải thích từng bước:

1. `@interface Info` khai báo một **loại annotation**, gồm `author()` bắt buộc và `version()` mặc định là `1`.
2. `@Target(ElementType.METHOD)` giới hạn `@Info` dùng trên khai báo phương thức. Gắn nó lên một lớp sẽ bị compiler từ chối.
3. `@Retention(RetentionPolicy.RUNTIME)` yêu cầu giữ metadata của `@Info` để code đang chạy có thể truy xuất bằng Reflection.
4. `@Info(author = "Lan", version = 2)` đặt hai giá trị metadata lên phương thức `process()`.
5. `getDeclaredMethod("process")` lấy đối tượng Reflection mô tả phương thức; `getAnnotation(Info.class)` đọc annotation; `author()` và `version()` đọc hai giá trị.

Quan sát quan trọng: kết quả **không có dòng `Đang xử lý`**, vì `main` chưa từng gọi `process()`. Chỉ gắn và đọc annotation không kích hoạt thân phương thức. Để có hành vi thực tế, ta phải viết mã xử lý metadata, hoặc giao cho framework có hỗ trợ xử lý annotation ấy.

Nếu bỏ `version = 2` khỏi nơi sử dụng, `info.version()` trả về giá trị mặc định `1`. Nếu loại bỏ `@Retention(RetentionPolicy.RUNTIME)`, annotation tự định nghĩa sẽ mặc định có retention `CLASS`; lời gọi `getAnnotation(Info.class)` thông thường trả về `null`, nên ví dụ cần được điều chỉnh trước khi truy xuất phần tử.

## 5. Annotation được giữ ở đâu và đọc khi nào?

Annotation bắt đầu trong **mã nguồn**. Tùy chính sách lưu giữ (*retention policy*), thông tin đó có thể chỉ hữu ích lúc biên dịch hoặc còn được ghi vào tệp `.class`.

| `RetentionPolicy` | Có trong mã nguồn? | Có được lưu vào `.class`? | Đọc được bằng Reflection thông thường lúc chạy? |
| --- | --- | --- | --- |
| `SOURCE` | Có | Không | Không |
| `CLASS` | Có | Có | Không |
| `RUNTIME` | Có | Có | Có |

Đây là hai luồng xử lý dễ gặp:

```text
Mã nguồn có @Annotation
    |
    +--> javac / annotation processor --> kiểm tra, cảnh báo, sinh mã khi biên dịch
    |
    +--> tệp .class (nếu retention là CLASS hoặc RUNTIME)
              |
              +--> Reflection / framework ở runtime
                   (chỉ đọc annotation có retention RUNTIME)
```

**Đừng nhầm `@Retention` với `@Target`:**

- `@Retention` quyết định annotation tồn tại đến giai đoạn nào.
- `@Target` quyết định annotation có thể gắn ở vị trí nào.

Hai annotation này là **meta-annotation**: annotation dùng để mô tả chính một loại annotation khác. Những meta-annotation khác gồm `@Documented` (liên quan việc xuất hiện trong Javadoc), `@Inherited` (một số annotation trên lớp có thể được lớp con thừa hưởng theo quy tắc Reflection) và `@Repeatable` (cho phép xuất hiện lặp lại). Không phải annotation nào cũng dùng được ở mọi vị trí hoặc được tự động kế thừa.

## 6. Annotation được ứng dụng trong thực tế như thế nào?

**Trong Java thuần:**

- `@Override` giúp compiler kiểm tra ý định ghi đè phương thức. Ghi đè đúng vẫn xảy ra theo quy tắc Java kể cả khi không viết `@Override`, nhưng bỏ annotation sẽ mất một kiểm tra hữu ích.
- `@Deprecated` đánh dấu API không còn được khuyến khích sử dụng, để compiler và các công cụ đưa ra cảnh báo/thông tin. Nó không tự cấm gọi API.
- `@SuppressWarnings` điều chỉnh cảnh báo compiler trong phạm vi được hỗ trợ; chỉ nên dùng sau khi hiểu lý do phát sinh cảnh báo.

**Trong thư viện và framework (cần có thư viện cùng môi trường phù hợp):**

- `@Test`: JUnit phát hiện và chạy các phương thức kiểm thử thông qua test engine.
- `@Entity`: JPA provider đọc thông tin ánh xạ lớp sang thực thể quản lý.
- `@RestController` / `@GetMapping`: Spring Web nhận biết controller và tuyến HTTP khi ứng dụng có cấu hình, thành phần và cơ chế xử lý thích hợp.
- `@Transactional`: Spring có thể áp dụng ranh giới transaction thông qua cơ chế quản lý và interception đã cấu hình.

Các ví dụ thư viện này **không có sẵn trong Java SE**. Việc mã nguồn biên dịch được hay annotation xuất hiện ở runtime chưa đủ để hệ thống thực hiện hành vi mong muốn; phải có thành phần thực sự tiêu thụ metadata.

## 7. Metadata khác gì comment, cấu hình và trạng thái chạy?

| Hình thức | Mục đích chủ yếu | Ai sử dụng? |
| --- | --- | --- |
| Comment `// ...` | Diễn giải cho người đọc, bị bỏ qua khi biên dịch | Người phát triển |
| Javadoc `/** ... */` | Tạo tài liệu API có cấu trúc | Công cụ Javadoc, IDE, người đọc |
| Annotation `@...` | Gắn metadata có kiểu và quy tắc hợp lệ | Compiler, processor, framework, Reflection |
| Cấu hình ngoài (ví dụ tệp properties) | Giá trị thiết lập môi trường hoặc ứng dụng | Mã cấu hình và framework tương ứng |
| Biến/đối tượng runtime | Dữ liệu có thể thay đổi trong lúc chương trình chạy | Logic chương trình |

Ví dụ, “phương thức này có vai trò xử lý HTTP GET” là thông tin khai báo phù hợp với annotation của web framework. Ngược lại, “giá trị timeout của request vừa nhận là 150 ms” là dữ liệu runtime, không nên cố đưa vào phần tử annotation vì các giá trị annotation phải đáp ứng điều kiện hằng ở thời điểm biên dịch.

Dùng annotation khi nó giúp hệ thống diễn đạt một quy ước **ổn định và có bên xử lý rõ ràng**. Nếu một thông số cần thay đổi theo môi trường hoặc theo yêu cầu người dùng, hãy cân nhắc cấu hình hay dữ liệu runtime thay vì tạo thêm annotation.

## 8. Những nhầm lẫn phổ biến

1. **“Có annotation thì Java tự thực hiện chức năng.”** Sai. `@Override` có ý nghĩa vì compiler hiểu nó; `@Test` cần JUnit; `@Transactional` cần cơ chế Spring tương ứng. Một annotation tự viết nhưng không có code xử lý có thể chỉ là metadata nằm yên.
2. **“Mọi annotation đều đọc được bằng Reflection.”** Sai. Với API Reflection thông thường, loại annotation phải có retention `RUNTIME`; `SOURCE` và `CLASS` không được trả về theo cách đó.
3. **“Annotation là một comment đẹp hơn.”** Chưa đủ. Annotation được compiler kiểm tra cú pháp/kiểu, giới hạn vị trí bằng `@Target` và có thể được công cụ xử lý bằng API.
4. **“Giá trị annotation thay đổi như field của object.”** Sai. Phần tử annotation là metadata khai báo có giới hạn loại và giá trị, không phải trạng thái mutable của từng đối tượng.
5. **“Chỉ cần đánh dấu `@Deprecated` là code cũ không gọi được.”** Sai. Annotation giúp truyền tín hiệu và cảnh báo; việc chặn sử dụng phải do cơ chế khác đảm nhiệm.

## 9. Tự kiểm tra kiến thức

**Tình huống 1:** Bạn đặt `@Info(author = "Lan")` lên `process()` nhưng không bao giờ dùng Reflection hoặc một công cụ hiểu `@Info`. Phương thức có tự chạy không? **Không**; annotation mới chỉ mô tả metadata.

**Tình huống 2:** Bạn thay `@Retention(RUNTIME)` trong ví dụ bằng `@Retention(CLASS)`. Điều gì thay đổi? Annotation vẫn có trong `.class` nhưng `getAnnotation(Info.class)` bằng Reflection thông thường không thấy nó; nếu không kiểm tra `null`, việc truy cập `info.author()` sẽ ném `NullPointerException`.

**Tình huống 3:** Vì sao nên dùng `@Override` khi viết phương thức ghi đè? Vì compiler có thể phát hiện việc viết sai chữ ký hoặc không thực sự ghi đè như người viết dự định.

Điểm cốt lõi cần nắm: **annotation cung cấp metadata có cấu trúc về chương trình; compiler, công cụ hoặc framework mới quyết định metadata ấy tạo ra tác dụng gì, vào thời điểm nào.**

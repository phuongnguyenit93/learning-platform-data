# Quan hệ giữa nơi khai báo, nơi sử dụng và bên xử lý annotation trong Java

## 1. Ba vai trò khác nhau trong cùng một cơ chế

Khi nhìn thấy `@Something` trong Java, cần phân biệt **ba nơi/ba vai trò**:

1. **Nơi khai báo loại annotation (declaration)**: định nghĩa annotation *có tên gì, nhận những phần tử dữ liệu nào, được gắn ở đâu và được giữ đến giai đoạn nào*.
2. **Nơi sử dụng annotation (usage)**: gắn annotation lên một thành phần Java cụ thể và cung cấp giá trị metadata tại vị trí ấy.
3. **Bên xử lý annotation (consumer/processor)**: đọc metadata rồi quyết định **kiểm tra, sinh mã, cấu hình hoặc thực hiện một hành vi**.

Ba vai trò có thể xuất hiện trong các tệp, module hoặc thư viện khác nhau. Annotation là **hợp đồng biểu diễn metadata** kết nối nơi khai báo và nơi sử dụng với bên xử lý. Bản thân ký hiệu `@...` không thực thi nghiệp vụ, tự tạo đối tượng, tự ghi log hay tự mở transaction.

```text
Người/thư viện định nghĩa:
  @interface BusinessAction { ... }
               |
               | cung cấp loại annotation và các quy tắc
               v
Người viết nghiệp vụ sử dụng:
  @BusinessAction("BOOK_TICKET")
  void book() { ... }
               |
               | metadata gắn với một phương thức cụ thể
               v
Bên xử lý:
  compiler / annotation processor / framework / Reflection
               |
               v
  kiểm tra, phát sinh mã, đăng ký chức năng hoặc chạy logic
```

Dấu mũi tên cuối **chỉ xảy ra nếu có bên thực sự nhận diện và xử lý annotation**. Nơi định nghĩa và nơi sử dụng có thể hoàn toàn hợp lệ về cú pháp, nhưng nếu không có bên xử lý phù hợp thì hành vi mong đợi vẫn không xuất hiện.

## 2. Nơi khai báo: định nghĩa *loại* metadata

Định nghĩa một annotation tùy chỉnh bằng từ khóa `@interface`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface BusinessAction {
    String value();
    int level() default 1;
}
```

Đây là **khai báo một annotation type**, chưa gắn metadata lên phương thức nghiệp vụ nào và chưa viết cơ chế xử lý nào.

- `BusinessAction` là tên loại annotation.
- `value()` là phần tử bắt buộc kiểu `String`; nơi sử dụng phải cung cấp giá trị.
- `level()` là phần tử kiểu `int`, có mặc định `1`.
- `@Target(ElementType.METHOD)` giới hạn vị trí sử dụng vào khai báo phương thức.
- `@Retention(RetentionPolicy.RUNTIME)` yêu cầu lưu annotation để có thể đọc bằng Reflection tại runtime.

`@Target` và `@Retention` là **meta-annotation**: chúng mô tả một **loại annotation** khác. Chúng không phải dữ liệu nghiệp vụ của `book()`. Khi không khai báo `@Retention`, chính sách mặc định của annotation tự định nghĩa là `CLASS`: metadata được lưu trong `.class` nhưng không hiện diện qua API Reflection thông thường lúc chạy.

Các phần tử annotation có kiểu giới hạn: kiểu nguyên thủy, `String`, `Class`, enum, annotation khác hoặc mảng một chiều của những loại đó. Phần tử không phải biến mutable của một đối tượng; giá trị ghi tại nơi sử dụng phải đáp ứng quy tắc hằng ở thời điểm biên dịch. Bạn không thể đưa một đối tượng service, một request runtime hoặc một `new HashMap<>()` vào phần tử annotation.

**Ranh giới trách nhiệm:** người thiết kế `BusinessAction` tạo một giao diện metadata và phạm vi sử dụng hợp lệ. Khai báo `@interface` **không chứa thân hàm** để tự xử lý `level` hoặc `value`. Logic kiểm tra hay ghi audit phải được triển khai ở bên tiêu thụ metadata.

## 3. Nơi sử dụng: gắn *giá trị* metadata vào vị trí cụ thể

Sau khi có loại annotation, mã nghiệp vụ có thể gắn nó lên phương thức:

```java
class BookingService {
    @BusinessAction(value = "BOOK_TICKET", level = 2)
    public void book() {
        System.out.println("Dịch vụ: đã giữ chỗ");
    }
}
```

Đoạn mã này khai báo rằng **phương thức `book()`** mang metadata gồm `value="BOOK_TICKET"` và `level=2`.

- Nơi sử dụng tham chiếu một loại annotation đã khai báo, tuân theo tên, kiểu phần tử và `@Target` của loại đó.
- Metadata thuộc về thành phần được gắn; nó không tự biến thành một lệnh trong thân phương thức.
- Cùng `@BusinessAction` có thể được gắn trên nhiều phương thức với giá trị khác nhau; mỗi nơi gắn có metadata của riêng mình.
- Nếu viết `@BusinessAction("BOOK_TICKET")` thì Java hiểu giá trị đó thuộc phần tử tên `value`; `level` nhận giá trị mặc định `1`.
- Nếu viết `@BusinessAction` mà không truyền `value`, compiler báo lỗi vì `value()` không có mặc định. Nếu gắn lên class trong khi `@Target` chỉ cho `METHOD`, compiler cũng báo lỗi.

Điểm dễ nhầm: việc `book()` được gọi trực tiếp bằng `new BookingService().book()` vẫn chạy **thân phương thức Java như bình thường**. Nếu không có mã đọc annotation, sẽ không có dòng audit hay hành vi đặc biệt nào do `@BusinessAction` tự tạo ra.

## 4. Bên xử lý: metadata trở thành hành vi ở bước nào?

Nói “annotation có tác dụng” là nói đến việc **một bên có thẩm quyền xử lý nó**. Những bên xử lý phổ biến không giống nhau:

| Bên xử lý | Khi nào đọc? | Đọc bằng gì? | Ví dụ kết quả |
| --- | --- | --- | --- |
| Java compiler, với annotation được compiler hỗ trợ sẵn | Trong lúc biên dịch | Quy tắc của ngôn ngữ/trình biên dịch | `@Override` giúp kiểm tra phương thức thực sự override; `@SuppressWarnings` ảnh hưởng cảnh báo được chỉ định |
| Annotation processor do ứng dụng/thư viện đăng ký | Trong quá trình `javac` biên dịch | Annotation Processing API, các mô hình `Element`/`TypeMirror` | Phát hiện sai quy tắc, báo lỗi hoặc sinh tệp nguồn/tài nguyên |
| Runtime framework | Khi khởi động hoặc khi xử lý một tình huống | Metadata qua Reflection, công cụ đọc bytecode hoặc mô hình metadata của framework | JUnit tìm test; Spring Web đăng ký mapping; Spring Transaction áp dụng cơ chế transaction khi đủ điều kiện |
| Mã Java tự viết | Tại thời điểm mã đọc được gọi | `Class`, `Method`, `Field` và `getAnnotation(...)` trong Reflection | Kiểm tra quyền theo quy tắc tự viết, ghi audit hoặc chọn handler |

**Compiler hỗ trợ trực tiếp** và **annotation processor mở rộng** là hai dạng xử lý trong giai đoạn biên dịch, nhưng không đồng nghĩa với nhau. `@Override` có ý nghĩa ngôn ngữ được `javac` kiểm tra sẵn; một annotation tự định nghĩa không tự có những kiểm tra nghiệp vụ tương tự nếu chưa có processor hoặc consumer.

Một annotation processor cũng **không tự chạy chỉ vì bạn khai báo annotation**: processor cần được cung cấp/đăng ký qua cơ chế của công cụ build hoặc compiler. Runtime framework cũng phải được cài đặt, cấu hình và có điều kiện kích hoạt phù hợp.

## 5. Ví dụ Java 17+: đủ cả khai báo, sử dụng và xử lý

Tạo tệp **`AnnotationRelationshipDemo.java`** với toàn bộ mã dưới đây. Ví dụ độc lập, chỉ dùng JDK; công cụ xử lý chính là mã Reflection tự viết, nên dễ thấy chính xác chỗ metadata được biến thành hành vi.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

// [1] NƠI KHAI BÁO: định nghĩa metadata và quy tắc áp dụng.
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface BusinessAction {
    String value();
    int level() default 1;
}

class BookingService {
    // [2] NƠI SỬ DỤNG: gắn metadata vào phương thức cụ thể.
    @BusinessAction(value = "BOOK_TICKET", level = 2)
    public void book() {
        System.out.println("Dịch vụ: đã giữ chỗ");
    }
}

public class AnnotationRelationshipDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        BookingService service = new BookingService();

        System.out.println("[1] Gọi trực tiếp");
        service.book();

        System.out.println("[2] Bên xử lý annotation");

        // [3] BÊN XỬ LÝ: tìm đúng phương thức và đọc annotation.
        Method method = BookingService.class.getDeclaredMethod("book");
        BusinessAction metadata =
                method.getAnnotation(BusinessAction.class);

        if (metadata == null) {
            System.out.println("Phương thức không có BusinessAction");
            return;
        }

        System.out.println("Metadata: "
                + metadata.value() + ", level=" + metadata.level());

        if (metadata.level() >= 2) {
            System.out.println("Ghi audit: " + metadata.value());
        }

        // Chính consumer chủ động gọi phương thức; annotation không tự gọi.
        method.invoke(service);
    }
}
```

Tại thư mục chứa tệp, biên dịch và chạy:

```bash
javac -encoding UTF-8 AnnotationRelationshipDemo.java
java AnnotationRelationshipDemo
```

Kết quả chuẩn trên terminal hỗ trợ Unicode:

```text
[1] Gọi trực tiếp
Dịch vụ: đã giữ chỗ
[2] Bên xử lý annotation
Metadata: BOOK_TICKET, level=2
Ghi audit: BOOK_TICKET
Dịch vụ: đã giữ chỗ
```

### Phân tích luồng thực thi

**Giai đoạn khai báo và biên dịch:** `javac` kiểm tra annotation `@BusinessAction` có thể gắn lên phương thức, phần tử `value` đúng kiểu `String`, `level` đúng kiểu `int`. Vì có `RetentionPolicy.RUNTIME`, thông tin annotation được ghi vào bytecode theo cách runtime có thể truy xuất.

**Lần gọi trực tiếp:** `service.book()` chỉ in dòng `Dịch vụ: đã giữ chỗ`. Không xuất hiện `Metadata` hay `Ghi audit` vì phần gọi này không có consumer đọc annotation.

**Lần gọi qua consumer:** mã lấy phương thức bằng `getDeclaredMethod("book")`, đọc annotation bằng `getAnnotation(BusinessAction.class)`, lấy hai phần tử metadata, áp dụng quy tắc `level >= 2` để in audit rồi gọi phương thức bằng `method.invoke(service)`. Đây là logic *do người viết consumer lựa chọn*; Java không suy luận được rằng `level=2` có nghĩa “phải ghi audit”.

Dòng kiểm tra `metadata == null` có ý nghĩa thực tế: có thể một phương thức không được gắn annotation hoặc annotation không được lưu cho Reflection. Không nên giả định `getAnnotation(...)` luôn trả về một đối tượng.

### Ba thay đổi nhỏ giúp tự kiểm chứng

1. Xóa lời gọi `method.invoke(service)`: bên xử lý vẫn đọc metadata và in audit, nhưng phương thức `book()` chỉ chạy ở lần gọi trực tiếp.
2. Xóa `@BusinessAction(...)` trên `book()`: dòng gọi trực tiếp vẫn hoạt động; consumer in thông báo không có annotation rồi dừng.
3. Thay `RetentionPolicy.RUNTIME` thành `RetentionPolicy.CLASS`: annotation vẫn có thể nằm trong `.class`, nhưng `getAnnotation(...)` không tìm thấy qua Reflection thông thường; không có phần metadata/audit của consumer.

Những thay đổi này chứng minh **có nơi khai báo + nơi sử dụng chưa bảo đảm có hành vi**: cần có một bên xử lý và một điểm thực sự kích hoạt bên đó.

## 6. Annotation đi từ mã nguồn đến compiler và runtime

Nơi khai báo quyết định sự hiện diện của metadata ở các giai đoạn khác nhau thông qua retention policy:

| Retention | Trong source | Trong `.class` | Reflection chuẩn tại runtime |
| --- | --- | --- | --- |
| `RetentionPolicy.SOURCE` | Có | Không | Không |
| `RetentionPolicy.CLASS` | Có | Có | Không |
| `RetentionPolicy.RUNTIME` | Có | Có | Có |

Lưu ý: metadata `CLASS` vẫn có thể được **công cụ đọc bytecode** xử lý; cột cuối chỉ nói về API Reflection chuẩn. Một annotation `SOURCE` vẫn có thể được compiler hoặc annotation processor phân tích **trong lúc biên dịch**. Vì vậy, `RUNTIME` không phải “loại tốt nhất cho mọi annotation”; phải chọn theo **bên nào cần đọc và vào lúc nào**.

```text
                 MÃ NGUỒN JAVA
           ┌─────────────────────────┐
           │ Khai báo @interface     │
           │ Gắn @BusinessAction(...)│
           └────────────┬────────────┘
                        │
                        v
                 JAVAC / BUILD
       ┌────────────────┴────────────────┐
       │ Kiểm tra cú pháp, @Target,      │
       │ kiểu và giá trị phần tử         │
       │                                 │
       │ Annotation processor được       │
       │ đăng ký: kiểm tra / sinh mã     │
       └────────────────┬────────────────┘
                        │
                        v
          .class (theo retention)
                        │
                        v
              ỨNG DỤNG CHẠY
       ┌────────────────┴────────────────┐
       │ Consumer runtime nhận diện      │
       │ annotation rồi áp dụng quy tắc  │
       └─────────────────────────────────┘
```

Không phải mọi hệ thống đều có đầy đủ từng nhánh. Annotation chỉ dành cho compile-time có thể hoàn thành mục đích trước khi chạy; annotation dành cho Reflection cần `RUNTIME`.

Cũng không nên nhầm `@Target` với `@Retention`: `@Target` giới hạn **vị trí gắn**, còn `@Retention` kiểm soát **giai đoạn lưu giữ**. Chọn được vị trí gắn hợp lệ không đồng nghĩa runtime có thể đọc được annotation đó.

## 7. Mối quan hệ trong ứng dụng thực tế

Giả sử xây hệ thống đặt vé dùng một framework web:

- **Nhà thiết kế thư viện/framework** khai báo loại annotation (chẳng hạn annotation chỉ rõ HTTP mapping), đồng thời viết consumer để quét, đăng ký và định tuyến.
- **Người viết ứng dụng** gắn annotation lên phương thức controller với đường dẫn hoặc loại HTTP cần xử lý.
- **Framework chạy** đọc metadata ở các vị trí hợp lệ, đăng ký tuyến tương ứng và sau đó chuyển request đến handler khi có request phù hợp.

Với Spring, ví dụ `@GetMapping("/tickets")` mô tả mapping; ứng dụng cần thành phần Spring Web và cấu hình controller thích hợp để mapping được đăng ký và sử dụng. Với JUnit, `@Test` đánh dấu phương thức; test engine quyết định phương thức nào được chạy. Với Spring `@Transactional`, metadata là một đầu vào cho cơ chế transaction của framework; chỉ đặt annotation trong mã chưa chứng minh rằng mọi đường gọi đều được intercept hay có transaction thực tế.

Những ví dụ trên đều thuộc **thư viện ngoài Java SE**; chúng không cần thiết để biên dịch ví dụ `AnnotationRelationshipDemo.java`.

Một kiểu ứng dụng khác là **annotation processor tại compile-time**: thư viện cung cấp annotation `@GenerateSomething` và processor đã đăng ký. Processor có thể duyệt các thành phần mang annotation rồi sinh thêm mã nguồn. Mã mới phải được compiler xử lý như một phần quy trình build. Annotation **không tự biến đổi nội dung thân phương thức Java đã viết**; bất kỳ thay đổi hành vi nào đều phải xuất phát từ công cụ hoặc cơ chế xử lý cụ thể.

### Ai phụ thuộc vào ai?

Về cú pháp, **nơi sử dụng** phải biết loại annotation để compiler kiểm tra. **Bên xử lý** cũng phải nhận diện được loại annotation hoặc quy ước metadata tương ứng để xử lý. Nhưng logic nghiệp vụ không cần gọi consumer trực tiếp nếu framework tổ chức luồng đó; điều này làm metadata trở thành một cách nối mã khai báo với một cơ chế dùng chung.

Cơ chế này hữu ích cho những chức năng lặp lại (ví dụ mapping, validation, kiểm thử, serialization, transaction) nếu bên xử lý đã tồn tại và luật hoạt động đủ rõ. Nó có thể gây khó debug nếu người học không biết **consumer nào chạy, chạy vào lúc nào, trên những đối tượng/phương thức nào**.

## 8. Các lỗi tư duy thường gặp

1. **Nhầm định nghĩa annotation với triển khai tính năng.** Viết `@interface Audit` chỉ tạo ra loại metadata. Chưa có consumer thì không tự sinh log.
2. **Nhầm gắn annotation với chạy code.** `@BusinessAction` trên `book()` không tự làm `book()` chạy, như lần gọi trực tiếp trong ví dụ.
3. **Không xác định ai đọc annotation.** Một ý tưởng “đánh dấu phương thức cần kiểm tra” chưa đủ; phải chỉ rõ compiler, processor, framework hay mã Reflection nào áp dụng quy tắc kiểm tra.
4. **Dùng `CLASS` rồi trông đợi `getAnnotation(...)` thấy được.** Reflection chuẩn cần annotation có retention `RUNTIME`; `CLASS` phục vụ các công cụ đọc bytecode hoặc nhu cầu build phù hợp.
5. **Nhầm quyền của consumer với quyền của annotation.** Gắn `@RequiresRole("ADMIN")` tự viết lên một phương thức không bảo vệ phương thức nếu không có cơ chế xác thực và kiểm tra quyền thực sự chạy trên mọi đường gọi cần bảo vệ.
6. **Nhầm tất cả annotation với annotation runtime.** `@Override` có ích ngay trong compiler; không cần consumer Reflection lúc chương trình chạy.
7. **Quên vị trí sử dụng.** Annotation có `@Target(ElementType.METHOD)` không thể gắn tùy ý lên class hoặc field. Một processor/consumer cũng có thể chỉ quét một phạm vi nhất định, nên đúng kiểu annotation thôi chưa đủ.

## 9. Cách phân tích một annotation bất kỳ

Khi gặp một annotation lạ trong dự án, hãy lần theo chuỗi câu hỏi:

1. **Nó được khai báo ở đâu?** Xác định package/thư viện chứa `@interface` và các phần tử có thể truyền vào.
2. **Nó được phép gắn ở đâu?** Đọc `@Target`, xem annotation đang gắn đúng class/phương thức/field/tham số hay vị trí hợp lệ khác.
3. **Ai cung cấp dữ liệu?** Xem giá trị được viết tại nơi sử dụng, giá trị mặc định, và sự khác nhau giữa những vị trí sử dụng.
4. **Ai là consumer?** Compiler built-in, annotation processor của build, framework nào, hay Reflection tự viết?
5. **Consumer chạy khi nào và được kích hoạt thế nào?** Compile-time, bootstrap, lúc nhận request, lúc chạy test hoặc lúc một phương thức consumer được gọi?
6. **Consumer có thật sự nhìn thấy annotation không?** Kiểm tra retention, phạm vi quét, đối tượng đang được xử lý và cách truy xuất metadata.
7. **Hành vi quan sát được do đoạn code nào tạo ra?** Đối chiếu log, mã handler/processor và kết quả thực thi; đừng suy từ tên annotation.

### Bài tập tự kiểm tra

**Bài 1.** Khai báo `@interface Flag { String value(); }` rồi gắn `@Flag("IMPORTANT")` lên một method, không viết processor và không có runtime consumer. Điều gì xảy ra? — Nếu nơi sử dụng hợp lệ và biên dịch thành công, metadata đơn thuần không làm phương thức tự thực hiện nghiệp vụ.

**Bài 2.** Một thư viện có annotation `@Retention(SOURCE)` và annotation processor chạy ở `javac`. Processor có dùng được annotation không? — Có, xử lý tại compile-time không đòi hỏi metadata sống đến runtime.

**Bài 3.** Trong ví dụ chạy được, bạn đổi `level=2` thành `level=1`. Có còn in audit không, và `book()` có chạy không? — Không còn in audit vì điều kiện `level >= 2` sai; `book()` vẫn chạy hai lần (một lần trực tiếp, một lần do `method.invoke(service)`), nếu không sửa phần consumer khác.

**Bài 4.** Vì sao annotation có thể hiện diện mà Spring/JUnit không tạo hành vi mong muốn? — Cần đúng runtime engine, cấu hình, điều kiện kích hoạt và đường gọi mà framework hỗ trợ.

Quan hệ cần nhớ là: **nơi khai báo định nghĩa hình dạng và quy tắc metadata; nơi sử dụng cung cấp metadata cho một thành phần cụ thể; bên xử lý đọc metadata ở giai đoạn thích hợp và chủ động thực hiện hành vi**.

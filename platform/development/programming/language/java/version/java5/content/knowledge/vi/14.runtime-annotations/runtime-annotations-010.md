# Giới hạn giữa siêu dữ liệu và cơ chế thực thi nghiệp vụ

## Khái niệm: annotation mô tả, thành phần xử lý mới tạo hành vi

Annotation là siêu dữ liệu gắn vào khai báo hoặc vị trí sử dụng kiểu trong chương trình. Nó có thể biểu thị một quy tắc, một cấu hình hoặc một ý định cần công cụ khác hiểu.

Ví dụ, `@TextRule(rejectBlank = true)` có thể mô tả yêu cầu không chấp nhận chuỗi rỗng. Nhưng riêng dòng annotation đó không chèn câu lệnh `if`, không tạo ngoại lệ và không chặn bất kỳ lời gọi nào.

Muốn có hành vi khi chạy, phải có mã:

1. Tìm đúng phần tử được gắn annotation.
2. Đọc giá trị siêu dữ liệu.
3. Diễn giải giá trị theo một quy tắc đã xác định.
4. Thực hiện việc kiểm tra, điều phối hoặc gọi nghiệp vụ ở đúng thời điểm.

Đặc tả Java trình bày annotation như một hình thức cung cấp thông tin cho công cụ tại [JLS §9.7](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7). Khi sử dụng annotation trong thiết kế, cần luôn chỉ ra thành phần nào đọc và áp dụng thông tin đó.

Bài dùng Java hiện đại, với ví dụ chạy được trên JDK 17 trở lên và không cần thư viện ngoài.

## Vì sao sự phân biệt này quan trọng?

Một khai báo trông có vẻ đầy đủ chưa chắc tạo ra đúng hành vi thực tế. Chương trình có thể có annotation đúng cú pháp nhưng:

- Không có thành phần nào biết kiểu annotation đó.
- Thành phần xử lý chưa được khởi tạo.
- Lời gọi đi thẳng vào đối tượng nghiệp vụ, không qua điểm xử lý.
- Công cụ đọc một phương thức khác với nơi annotation được khai báo.
- Giá trị cấu hình được đọc nhưng cách áp dụng chưa được triển khai.

Những trường hợp này thường không phải lỗi cú pháp của annotation. Chúng là vấn đề kết nối giữa **khai báo ý định** và **đường thực thi**.

Một câu hỏi hữu ích khi đọc mã là: “Nếu bỏ bộ xử lý, phần hành vi nào sẽ biến mất?” Nếu không chỉ ra được bộ xử lý cụ thể, đừng mặc nhiên coi annotation là một cơ chế thực thi.

## Ba trách nhiệm cần tách rõ

| Thành phần | Trách nhiệm | Không tự làm thay phần khác |
| --- | --- | --- |
| Kiểu annotation và lần sử dụng | Biểu diễn tên quy tắc, tùy chọn và giá trị cấu hình | Không tự chạy nghiệp vụ hoặc chặn lời gọi |
| Bộ xử lý annotation | Đọc, kiểm tra và diễn giải cấu hình; điều khiển phần việc được giao | Không tự biết mọi hợp đồng nghiệp vụ chỉ từ tên annotation |
| Mã nghiệp vụ | Thực hiện thao tác của miền ứng dụng và giữ các điều kiện cần của thao tác đó | Không mặc nhiên được bảo vệ ở mọi đường gọi chỉ vì có annotation |

Ví dụ, annotation có thuộc tính `boolean rejectBlank() default true;`. Gọi `annotation.rejectBlank()` chỉ đọc một giá trị boolean. Nó không kiểm tra một chuỗi nào cả.

Tương tự, một annotation có thuộc tính kiểu `Class<?>` chỉ cung cấp một giá trị tham chiếu kiểu. Java không tự tạo đối tượng của lớp đó và không tự gọi phương thức xử lý của nó. Nếu thiết kế dùng lớp được chỉ định như một bộ xử lý, phần tạo và gọi bộ xử lý vẫn phải được triển khai.

## Chuỗi từ khai báo đến tác động

Một cơ chế xử lý lúc chạy có thể được hình dung như sau:

```text
Khai bao annotation
        |
        v
Tim dung lop / phuong thuc / tham so
        |
        v
Doc va kiem tra gia tri metadata
        |
        v
Dien giai quy tac
        |
        v
Loi goi di qua diem ap dung
        |
        v
Kiem tra / dieu phoi / goi nghiep vu
```

Mỗi mũi tên đều là việc mà chương trình hoặc framework phải thực hiện. `@Retention(RUNTIME)` chỉ giúp annotation còn sẵn cho reflection; nó không tự nối toàn bộ chuỗi này.

API [AnnotatedElement](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html) cung cấp khả năng đọc annotation. Các phương thức như `getAnnotation` trả thông tin, không thay cho lời gọi phương thức nghiệp vụ.

## Retention quyết định khả năng đọc, không quyết định hành vi

| Retention | Siêu dữ liệu tồn tại đến đâu | Hệ quả thực hành |
| --- | --- | --- |
| `SOURCE` | Có trong nguồn, bị trình biên dịch loại khỏi đầu ra annotation | Có thể phục vụ công cụ xử lý nguồn; reflection lúc chạy không đọc được annotation đó |
| `CLASS` | Được ghi vào tệp class | Công cụ đọc class có thể dùng; không đủ cho reflection lúc chạy |
| `RUNTIME` | Được giữ lại cho JVM và reflection | Bộ xử lý lúc chạy có thể đọc, nhưng vẫn phải có mã áp dụng |

Theo [RetentionPolicy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/RetentionPolicy.html), đây là chính sách giữ annotation.

Một công cụ xử lý lúc biên dịch có thể đọc annotation rồi sinh mã thực thi. Khi ứng dụng chạy, chính **mã đã sinh** thực hiện công việc; không phải vì annotation nguồn tự chạy.

Do đó, cũng không được suy ra “không có annotation lúc chạy thì không thể có hành vi liên quan”. Cần biết cơ chế dùng siêu dữ liệu ở giai đoạn nào.

## Ví dụ đầy đủ: một annotation, hai đường gọi

Thí nghiệm tạo một annotation `@TextRule` và một phương thức `submit(String)`.

- Đường gọi trực tiếp chỉ chạy phương thức.
- Đường gọi qua `invokeChecked` đọc annotation, kiểm tra chuỗi rồi mới gọi phương thức.
- Bộ đếm `calls` cho thấy nghiệp vụ đã được thực hiện bao nhiêu lần.

Phần thân `submit` cố ý không tự kiểm tra chuỗi rỗng để quan sát rõ giới hạn của annotation. Đây là mô hình thử nghiệm, không phải khuyến nghị bỏ điều kiện quan trọng khỏi mã nghiệp vụ.

Lưu thành `MetadataExecutionDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

public class MetadataExecutionDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface TextRule {
        boolean rejectBlank() default true;
    }

    public static class SubmissionService {
        private int calls;

        @TextRule
        public String submit(String text) {
            calls++;
            return "accepted:" + text.length();
        }

        public int calls() {
            return calls;
        }
    }

    static String invokeChecked(SubmissionService target, String text)
            throws ReflectiveOperationException {
        Method method = SubmissionService.class.getDeclaredMethod(
                "submit", String.class);
        TextRule rule = method.getAnnotation(TextRule.class);

        if (rule != null && rule.rejectBlank()
                && (text == null || text.isBlank())) {
            throw new IllegalArgumentException("text must not be blank");
        }

        return (String) method.invoke(target, text);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        SubmissionService service = new SubmissionService();
        Method method = SubmissionService.class.getDeclaredMethod(
                "submit", String.class);

        System.out.println("annotationPresent="
                + method.isAnnotationPresent(TextRule.class));
        System.out.println("calls.before=" + service.calls());

        System.out.println("direct=" + service.submit(""));
        System.out.println("calls.afterDirect=" + service.calls());

        try {
            invokeChecked(service, "");
            System.out.println("guarded=unexpected-success");
        } catch (IllegalArgumentException ex) {
            System.out.println("guarded="
                    + ex.getClass().getSimpleName());
        }
        System.out.println("calls.afterRejected=" + service.calls());

        System.out.println("guarded.valid="
                + invokeChecked(service, "book"));
        System.out.println("calls.afterValid=" + service.calls());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 MetadataExecutionDemo.java
java MetadataExecutionDemo
```

Kết quả:

```text
annotationPresent=true
calls.before=0
direct=accepted:0
calls.afterDirect=1
guarded=IllegalArgumentException
calls.afterRejected=1
guarded.valid=accepted:4
calls.afterValid=2
```

## Đọc kết quả theo từng ranh giới

### 1. Đọc annotation chưa làm nghiệp vụ chạy

`method.isAnnotationPresent(TextRule.class)` trả `true`, nhưng `calls.before=0`.

Điều này cho thấy việc kiểm tra siêu dữ liệu không gọi `submit`. Không có đối tượng nghiệp vụ nào được xử lý chỉ vì annotation được tìm thấy.

### 2. Gọi trực tiếp không tự kích hoạt bộ xử lý

Lệnh `service.submit("")` in `direct=accepted:0` và làm bộ đếm thành 1.

Annotation vẫn nằm trên phương thức, nhưng lời gọi này không đi qua `invokeChecked`. Vì phần thân `submit` không có điều kiện từ chối chuỗi rỗng, lời gọi vẫn thực thi.

Không có quy tắc tổng quát của Java rằng “mọi lời gọi đến một phương thức có annotation đều phải bị chặn trước”.

### 3. Bộ xử lý quyết định chặn trước khi gọi

`invokeChecked(service, "")` đọc `TextRule`, thấy `rejectBlank = true`, rồi ném `IllegalArgumentException` trước khi gọi `method.invoke`.

`calls.afterRejected=1` chứng minh lần bị từ chối không chạy phần thân `submit`. Nếu chỉ kiểm tra rằng có ngoại lệ mà không xem tác động, có thể bỏ sót việc kiểm tra đã diễn ra quá muộn.

### 4. Đầu vào hợp lệ đi qua kiểm tra rồi mới chạy nghiệp vụ

`invokeChecked(service, "book")` qua được điều kiện, gọi phương thức và trả `accepted:4`. Bộ đếm tăng lên 2.

Tác động này đến từ các câu lệnh trong `invokeChecked` và `submit`. Annotation cung cấp một tùy chọn cho các câu lệnh đó.

## Reflection cũng không tự hiểu quy tắc nghiệp vụ

`Method.invoke` thực hiện một lời gọi phản chiếu. Nó không tự xem mọi annotation trên phương thức rồi chọn cách áp dụng.

Trong ví dụ, nếu bỏ khối đọc `TextRule` và điều kiện `if`, giữ lại mỗi `method.invoke(target, text)`, đường gọi phản chiếu cũng sẽ chấp nhận chuỗi rỗng như gọi trực tiếp.

Ngoài ra, phương thức nghiệp vụ ném lỗi trong quá trình gọi phản chiếu có thể được bọc trong `InvocationTargetException`. Cần phân biệt:

- Lỗi do bộ xử lý tự tạo trước khi gọi nghiệp vụ.
- Lỗi do nghiệp vụ ném ra khi đang được gọi.
- Lỗi do chính thao tác phản chiếu, như quyền truy cập hoặc đối số không phù hợp.

Ví dụ chính dùng điều kiện để ném lỗi trước lời gọi; nó không triển khai một cơ chế chuẩn hóa mọi loại lỗi phản chiếu. Chi tiết lời gọi có tại [Method.invoke](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)).

`invokeChecked` cũng được viết riêng cho `SubmissionService.submit(String)`, không phải một bộ thực thi tổng quát cho mọi chữ ký. Nếu phát triển thành công cụ dùng chung, phải xác định rõ chữ ký được hỗ trợ, cách tìm phương thức và cách xử lý giá trị trả về, ngoại lệ.

## Điểm chặn và đường gọi quan trọng hơn hình thức khai báo

Một bộ xử lý có thể được đặt dưới nhiều hình thức:

| Cách triển khai | Nơi hành vi thực sự nằm |
| --- | --- |
| Hàm gọi bao như ví dụ | Mã kiểm tra trước/sau lời gọi |
| Đối tượng bao hoặc proxy | Phương thức của đối tượng trung gian mà lời gọi đi qua |
| Bộ điều phối của framework | Mã tìm thành phần, đọc cấu hình và điều phối thực thi |
| Mã sinh lúc biên dịch | Các lớp/phương thức được công cụ tạo ra |
| Biến đổi bytecode có chủ đích | Mã đã được công cụ chèn hoặc thay đổi |

Các cơ chế này không có cùng phạm vi tác động. Phải xét cơ chế thực tế và cấu hình đang dùng.

Ví dụ, một proxy theo kiểu ủy quyền có thể xử lý các lời gọi đi qua chính proxy đó. Một lời gọi trực tiếp đến đối tượng đích có thể đi ngoài đường này. Không được từ đó suy ra quy tắc cho mọi framework, mọi dạng proxy hoặc mọi cách biến đổi bytecode; cần đọc hợp đồng của công cụ cụ thể.

Cùng tên annotation cũng không đủ tạo cùng hành vi trong hai thư viện. Bộ xử lý phải nhận diện đúng kiểu annotation và hỗ trợ đúng ngữ nghĩa của nó.

## Điều kiện nghiệp vụ cốt lõi nên được bảo vệ ở đâu?

Nếu một điều kiện phải đúng với **mọi cách gọi hợp lệ**, chỉ đặt annotation trên một phương thức không đủ chứng minh điều kiện đó được giữ.

Có thể bảo vệ điều kiện bằng:

- Kiểm tra trực tiếp trong phương thức hoặc đối tượng miền phù hợp.
- Kiểu dữ liệu đầu vào đã được xác thực và có quy trình tạo đối tượng rõ ràng.
- Một ranh giới gọi bắt buộc, được kiến trúc và khả năng truy cập bảo đảm.
- Cơ chế framework được cấu hình, kiểm chứng và áp dụng đúng phạm vi.

Lựa chọn phụ thuộc thiết kế, nhưng cần chỉ ra bằng chứng rằng mọi đường cần bảo vệ đều đi qua chỗ kiểm tra.

Ví dụ này cho thấy vì sao chỉ kiểm thử đường `invokeChecked` chưa đủ nếu mã khác vẫn được phép gọi trực tiếp `submit`. Nếu yêu cầu thật là “`submit` luôn từ chối chuỗi rỗng”, cần sửa ranh giới nghiệp vụ để bản thân yêu cầu ấy được giữ.

Không nhất thiết sao chép cùng một khối kiểm tra vào mọi nơi. Có thể dùng chung hàm kiểm tra hoặc kiểu dữ liệu phù hợp, đồng thời tách rõ kiểm tra đầu vào ở biên hệ thống và điều kiện của miền nghiệp vụ.

## Khi nào annotation là một lựa chọn phù hợp?

Annotation hữu ích khi cùng một loại quy tắc hoặc cấu hình cần được gắn có cấu trúc vào nhiều khai báo và có một cơ chế xử lý thống nhất.

Ví dụ về **ý định có thể được biểu diễn**, tùy công cụ triển khai:

- Đánh dấu phương thức cần đo thời gian.
- Mô tả cách ánh xạ dữ liệu vào tham số.
- Đánh dấu một thao tác để bộ điều phối ghi nhận sự kiện.
- Cấu hình một chính sách kiểm tra lặp lại ở nhiều điểm.

Trong từng trường hợp vẫn cần thiết kế hành vi cụ thể. Chẳng hạn, “đo thời gian” phải xác định đo đoạn nào và ghi kết quả ở đâu; “ghi nhận sự kiện” phải xác định ghi trước, sau hay khi lỗi.

Nếu chỉ có một nhánh điều kiện đơn giản ở một nơi, một hàm gọi trực tiếp có thể dễ hiểu hơn việc tạo thêm annotation, bộ quét và quy tắc ưu tiên. Không nên chọn annotation chỉ vì cú pháp ngắn hoặc tạo cảm giác khai báo hoàn chỉnh.

## Hợp đồng của bộ xử lý cần được định nghĩa

Để một annotation có ý nghĩa ổn định, nên trả lời được:

1. Nó được đọc trên lớp, phương thức, tham số hay một vị trí sử dụng kiểu?
2. Khi không có annotation, điều gì xảy ra?
3. Khi annotation có giá trị không hợp lệ hoặc không đọc được, xử lý ra sao?
4. Có xét interface, lớp cha hoặc phương thức ghi đè không?
5. Nếu nhiều nguồn cùng cung cấp cấu hình, nguồn nào ưu tiên?
6. Kiểm tra diễn ra trước hay sau khi nghiệp vụ đã tạo tác động?
7. Những đường gọi nào được bảo đảm đi qua bộ xử lý?

Trong ví dụ, `rule == null` có nghĩa là không áp dụng điều kiện từ chối chuỗi rỗng. Đây là quyết định của `invokeChecked`, không phải một quy tắc mặc định chung của Java.

Tương tự, `default true` trong khai báo `TextRule` chỉ là giá trị mặc định của thuộc tính annotation. Nó chỉ tác động đến hành vi vì bộ xử lý đã đọc và dùng giá trị ấy.

## Lỗi phổ biến và cách kiểm tra

| Hiểu nhầm | Điều cần đối chiếu |
| --- | --- |
| Có `RUNTIME` là tự thực thi | Tìm mã đọc annotation và mã áp dụng |
| Annotation đúng cú pháp thì cơ chế đã hoạt động | Kiểm tra khởi tạo và cấu hình thành phần xử lý |
| Reflection gọi phương thức sẽ tự áp dụng annotation | Kiểm tra phần xử lý có được gọi trước `Method.invoke` không |
| Mọi đường gọi đều được bảo vệ | Vẽ đường gọi trực tiếp, qua đối tượng bao và qua bộ điều phối |
| Đọc được annotation là cấu hình hợp lệ | Kiểm tra các thuộc tính cần dùng và ngữ nghĩa của chúng |
| Annotation trên khai báo nào cũng được công cụ tìm thấy | Xác định đúng phần tử được đọc và quy tắc tìm nguồn |
| Ngoại lệ xuất hiện là chứng minh đã chặn đúng lúc | Kiểm tra tác động nghiệp vụ có xảy ra trước ngoại lệ không |

Không sửa triệu chứng bằng cách thêm annotation ở nhiều nơi mà chưa biết bộ xử lý đang đọc phần tử nào. Trước tiên hãy xác định chính xác điểm nối bị thiếu.

## Kiểm chứng hành vi thay vì chỉ kiểm tra sự hiện diện

Một kiểm tra như `isAnnotationPresent(...) == true` chỉ chứng minh metadata được nhìn thấy qua API đó. Nó không chứng minh quy tắc đã được thực hiện.

Các trường hợp kiểm chứng có ý nghĩa gồm:

- Đầu vào hợp lệ được xử lý đúng một lần.
- Đầu vào không hợp lệ bị chặn trước tác động nghiệp vụ.
- Tùy chọn annotation thay đổi đúng phần hành vi đã định nghĩa.
- Việc thiếu annotation có kết quả đúng hợp đồng.
- Những đường gọi nằm trong phạm vi thiết kế thực sự đi qua cơ chế áp dụng.
- Lỗi từ nghiệp vụ được phân biệt với lỗi của bộ xử lý.

Bộ đếm trong ví dụ là một bằng chứng đơn giản cho thứ tự thực thi. Với hệ thống khác, bằng chứng có thể là một thay đổi trạng thái, lời gọi tới thành phần phụ thuộc hoặc sự kiện được ghi nhận theo hợp đồng.

## Thực hành kiểm chứng

1. Chạy chương trình và đối chiếu đủ tám dòng output.
2. Đổi thành `@TextRule(rejectBlank = false)`. Khi đó `invokeChecked(service, "")` sẽ không ném lỗi kiểm tra, dòng `guarded=unexpected-success` xuất hiện và bộ đếm tiếp tục tăng. Dòng này là dấu hiệu từ bộ thử nghiệm, không phải lỗi mà Java tự tạo.
3. Khôi phục annotation, rồi gọi trực tiếp `method.invoke(service, "")` mà không qua khối kiểm tra; xác nhận reflection không tự áp dụng quy tắc.
4. Chuyển kiểm tra chuỗi rỗng vào đầu `submit`, trước `calls++`. Đối chiếu cách gọi trực tiếp cũng được bảo vệ khi điều kiện nằm trong ranh giới nghiệp vụ.
5. Bỏ annotation và mô tả hành vi của bộ xử lý theo nhánh `rule == null`, thay vì dự đoán từ tên hàm.

Điều cần nắm là mối nối cụ thể: **siêu dữ liệu biểu diễn quy tắc; mã xử lý và đường gọi quyết định quy tắc có được thực thi, ở đâu và vào lúc nào**.

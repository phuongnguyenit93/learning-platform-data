# Tổng kết tiêu chí chọn tính năng Java 5 trong ứng dụng Java hiện đại

## 1. Chọn theo vấn đề cần giải quyết

Nhiều nền tảng quan trọng của Java hiện đại được phổ biến từ Java 5: generics, enum, annotation, vòng lặp for mở rộng, autoboxing và các công cụ đồng thời. Chúng vẫn có giá trị khi được sử dụng theo hợp đồng và môi trường triển khai hiện nay.

Câu hỏi khi thiết kế không phải “có thể đưa thêm tính năng nào vào đây?”, mà là:

> Tính năng này giúp biểu diễn yêu cầu hoặc loại bỏ loại lỗi nào, và chi phí đi kèm có phù hợp không?

Một chương trình dùng ít tính năng nhưng có hợp đồng rõ ràng thường dễ kiểm chứng hơn chương trình cố kết hợp nhiều kỹ thuật trong cùng một đoạn mã.

Cần phân biệt:

- **Nguồn gốc tính năng:** giúp hiểu vì sao Java có công cụ đó.
- **Cách sử dụng hiện hành:** phụ thuộc JDK, API, thư viện và chính sách triển khai thật.
- **Ví dụ học tập:** chứng minh một hành vi có giới hạn, không tự trở thành thiết kế triển khai hoàn chỉnh.

Không giữ nguyên cấu hình runtime, giao thức bảo mật hoặc mẹo tối ưu cũ chỉ vì đang học một module có tên Java 5.

## 2. Sáu tiêu chí trước khi quyết định

| Tiêu chí | Câu hỏi cần trả lời |
| --- | --- |
| Đúng yêu cầu | Có loại lỗi hoặc nhu cầu cụ thể mà công cụ này giải quyết không? |
| Đúng mô hình | Dữ liệu là một lựa chọn, một tập cờ, một quan hệ kiểu hay một công việc bất đồng bộ? |
| Đúng hợp đồng | API bảo đảm điều gì, và những điều nào vẫn do ứng dụng chịu trách nhiệm? |
| Đúng chi phí | Có thêm cấp phát, khóa, luồng, độ trễ, tài nguyên hoặc cấu hình vận hành không? |
| Đúng môi trường | JDK và thư viện thực tế có hỗ trợ, còn được duy trì và được phép sử dụng không? |
| Kiểm chứng được | Có bằng chứng biên dịch, test hành vi, ca lỗi hoặc phép đo phù hợp không? |

Nếu không nêu được lợi ích cụ thể, chưa có lý do thêm công cụ. Nếu không nêu được đường lỗi và trách nhiệm dọn tài nguyên, thiết kế chưa hoàn chỉnh dù đường thành công chạy được.

## 3. Chọn công cụ biểu diễn kiểu và miền dữ liệu

### Generics: đưa quan hệ kiểu vào hợp đồng API

Dùng generics khi dữ liệu hoặc kết quả có quan hệ kiểu cần được giữ lại, ví dụ `List<Order>`, `Repository<ID,T>` hoặc một thuật toán dùng lại trên nhiều kiểu tương thích.

Giới hạn kiểu giúp phương thức dựa vào khả năng thật của đối tượng. Wildcard giúp nhận nguồn kiểu con hoặc đích kiểu cha theo luồng đọc/ghi. Không biến mọi tham số thành `Object` rồi ép kiểu ở cuối.

Cần tránh:

- Kiểu thô và cảnh báo unchecked bị bỏ qua mà không có chứng minh.
- Wildcard làm chữ ký khó đọc nhưng không mở thêm cách dùng hợp lệ.
- Tổng quát hóa một thuật toán vốn chỉ có một hợp đồng miền cụ thể.
- Giả định generics tự xác minh mọi điều kiện runtime hoặc giữ nguyên toàn bộ tham số kiểu để phản chiếu.

Các quy tắc kiểu có tham số được quy định trong [JLS mục 4.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5).

### Enum: một miền lựa chọn hữu hạn

Dùng enum cho một tập giá trị được mô hình hóa trong mã, chẳng hạn trạng thái hoặc kênh xử lý. Nó giúp tránh lỗi gõ chuỗi và làm chữ ký có nghĩa.

Nếu giá trị do người dùng tự tạo không có miền đóng ổn định, một enum có thể không phù hợp. Nếu cần tương thích dữ liệu ngoài, thiết kế mã định danh rõ ràng; không lưu vị trí khai báo làm hợp đồng bền vững.

### EnumSet và EnumMap: chọn theo hình dạng dữ liệu

- Nhiều cờ cùng bật: `EnumSet<Option>`.
- Một hằng enum gắn một giá trị: `EnumMap<Key,Value>`.
- Chỉ được chọn đúng một chế độ: một giá trị enum đơn lẻ.
- Tùy chọn kèm số, chuỗi hoặc thời hạn: một đối tượng cấu hình có trường tương ứng.

`EnumSet` mutable và không tự đồng bộ. Cần kiểm soát quyền sửa và sao chép khi đi qua ranh giới API. Hợp đồng nằm trong [EnumSet API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html); quy tắc enum nằm trong [JLS mục 8.9](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9).

## 4. Chọn cú pháp để tăng khả năng đọc, không che hành vi

| Tính năng | Nên dùng khi | Điều cần kiểm tra |
| --- | --- | --- |
| For mở rộng | Duyệt từng phần tử của mảng/Iterable | Cần chỉ số, sửa cấu trúc khi duyệt hoặc duyệt đặc biệt không? |
| Autoboxing/unboxing | Kết nối primitive với API kiểu tham chiếu | Có null, chi phí cấp phát hoặc so sánh sai bằng == không? |
| Varargs | Số đối số biến đổi giúp lời gọi rõ hơn | Có trường hợp rỗng, null, mơ hồ overload hoặc generic varargs không an toàn không? |
| Static import | Tên ngắn hơn mà vẫn rõ nguồn/nghĩa | Có làm người đọc khó biết thành viên từ đâu hoặc gây trùng tên không? |

Autoboxing là tiện ích cú pháp, không thay đổi bản chất:

- Unboxing một wrapper null có thể ném `NullPointerException`.
- `==` giữa các wrapper có thể là so sánh tham chiếu; không dựa vào cache wrapper để so sánh giá trị.
- Một vòng lặp số học nóng có thể cần primitive và phép đo phù hợp, không chỉ viết ngắn nhất.

Varargs không biến một mảng mutable thành dữ liệu riêng của phương thức. Với generic varargs, phải hiểu nguy cơ heap pollution; annotation khẳng định an toàn không thay thế chứng minh về cách phương thức sử dụng mảng.

Không dùng cú pháp ngắn để che thời gian chờ, tác dụng phụ hoặc quyền sở hữu dữ liệu.

## 5. Annotation cần có bên hiểu và xử lý nó

Annotation là metadata gắn với chương trình. Nó không tự khiến xác thực, giao dịch hoặc retry xảy ra.

Trước khi tạo hoặc dùng annotation, xác định:

1. Ai đọc nó: compiler, bộ xử lý annotation, thư viện hay mã phản chiếu?
2. Nó cần tồn tại ở giai đoạn nào?
3. Nó được phép đặt trên phần tử nào?
4. Hợp đồng khi thiếu, lặp hoặc cấu hình sai là gì?
5. Một interface hoặc phương thức gọi trực tiếp có biểu đạt rõ hơn không?

`@Override` có giá trị vì compiler kiểm tra hợp đồng ghi đè. Một annotation tùy tạo chỉ có ý nghĩa hành vi nếu có cơ chế xử lý tương ứng. `@Retention(RUNTIME)` làm metadata khả dụng ở runtime theo quy tắc, không tự thực thi mã.

Các quy tắc khai báo và sử dụng nằm trong [JLS chương 9](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6).

## 6. Chỉ thêm đồng thời khi có nhu cầu thực thi rõ ràng

Nhiều luồng có thể hữu ích để chồng lấp thời gian chờ hoặc khai thác CPU theo cấu trúc bài toán. Chúng cũng thêm hàng đợi, quyền sở hữu tài nguyên, lỗi bất đồng bộ và cơ chế kết thúc.

| Nhu cầu | Công cụ có thể phù hợp | Điều không được suy ra |
| --- | --- | --- |
| Chạy công việc và thu kết quả | ExecutorService, Callable, Future | Có Future không có nghĩa đã kiểm tra lỗi |
| Tách nguồn tạo việc và nơi xử lý | BlockingQueue có giới hạn phù hợp | Queue không tự có giao nhận bền vững hoặc đóng |
| Cập nhật một giá trị độc lập theo thao tác nguyên tử | Nhóm atomic | Nhiều thao tác ghép lại không tự thành một giao dịch |
| Bảo vệ bất biến qua nhiều trường/thao tác | synchronized hoặc Lock phù hợp | Không được giữ khóa tùy ý qua chờ lâu |
| Chia sẻ cấu trúc dữ liệu | Collection đồng thời phù hợp | Mọi chuỗi check-then-act đều không tự nguyên tử |

Mô hình bộ nhớ vẫn quyết định việc nhìn thấy và thứ tự thao tác. `volatile` không tự biến `count++` thành một thao tác nguyên tử. Ngược lại, thêm khóa khắp nơi mà không xác định bất biến có thể tạo tranh chấp hoặc chờ vòng.

Quy tắc happens-before được trình bày trong [JLS mục 17.4.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5). Các nhóm công cụ và bảo đảm đồng thời nằm trong [java.util.concurrent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html).

Trước khi thêm executor, trả lời được:

- Ai sở hữu và shutdown nó?
- Có bao nhiêu công việc được phép chờ?
- Mỗi I/O và toàn bộ tác vụ có thời hạn nào?
- Lỗi được quan sát ở đâu?
- Cancel có được bên xử lý đáp ứng không?
- Tác dụng phụ đã xảy ra xử lý thế nào khi một phần thất bại?

Lựa chọn mô hình luồng phải theo JDK và đặc tính tải hiện tại. Không coi một kích thước pool hay một công thức số luồng là đúng cho mọi dịch vụ.

## 7. Chọn API văn bản và dữ liệu theo đơn vị thật

Dữ liệu quốc tế không bảo đảm mỗi ký tự là một char. Khi đếm/cắt, cần biết yêu cầu nói về byte, code unit UTF-16, code point hay grapheme.

Ví dụ quyết định:

| Yêu cầu | Cách tiếp cận |
| --- | --- |
| Giới hạn kích thước bản tin UTF-8 | Đếm byte theo UTF-8, không lấy String.length làm số byte |
| Duyệt mã Unicode bổ sung | API code point với int |
| Cắt tiêu đề theo cụm hiển thị | Phân đoạn grapheme phù hợp |
| Đọc dữ liệu có định dạng máy | Charset, locale, giới hạn và chính sách lỗi tường minh |

Các overload char và int có phạm vi xử lý khác nhau, theo [Character API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html).

Với công cụ phân tích/định dạng như Scanner hoặc Formatter, kiểm tra locale, charset, kiểu số, kích thước dữ liệu và quyền đóng nguồn. Tiện ích nhập/xuất không thay thế hợp đồng định dạng. Một công cụ phù hợp cho tệp nhỏ hoặc dòng lệnh không tự là lựa chọn tốt nhất cho mọi đường xử lý tải cao.

## 8. Công cụ runtime cần câu hỏi chẩn đoán cụ thể

Các API quản lý và thông tin luồng có ích khi cần trả lời một vấn đề quan sát được, chẳng hạn luồng nào chờ khóa, heap tăng ở đâu hoặc CPU đang bị dùng bởi phần nào.

Không dùng một snapshot trạng thái luồng làm điều kiện đồng bộ nghiệp vụ. Không kết luận một đối tượng còn sống là rò rỉ chỉ vì heap đang dùng cao ở một thời điểm.

Khi đánh giá hiệu năng:

1. Đặt mục tiêu thông lượng, độ trễ và ngân sách bộ nhớ.
2. Thu đường cơ sở cùng phiên bản JDK, cấu hình và dữ liệu tải.
3. Thay một yếu tố có chủ đích.
4. Đo cả đường thành công, lỗi, timeout và mức tài nguyên.
5. Chọn thay đổi đáp ứng ràng buộc, không chỉ một con số đẹp.

Không bê nguyên các cờ GC từ cấu hình cũ sang collector hiện đại. Dữ liệu đo phải giải thích được giả thuyết tuning.

## 9. API bảo mật chọn theo giao thức và mô hình tin cậy

Một tính năng vẫn tồn tại trong API không có nghĩa mọi cơ chế, thuật toán hoặc cấu hình lịch sử của nó vẫn phù hợp.

Với TLS, cần kiểm tra phiên bản giao thức, danh tính đối tác, chuỗi chứng thư và việc quản lý tài nguyên. Dùng `SSLEngine` khi thật sự cần tích hợp tầng vận chuyển riêng và có khả năng quản lý đầy đủ máy trạng thái, bộ đệm, tác vụ và đóng kết nối.

Nếu thư viện giao thức cấp cao đã xử lý đúng TLS, tự viết lại toàn bộ SSLEngine chỉ để “dùng tính năng Java” có thể làm tăng rủi ro.

Với SASL, chọn theo phần tích hợp của giao thức, cơ chế đang được duy trì, khả năng của hai phía và chính sách bảo vệ kênh. Tạo được đối tượng cơ chế hoặc hoàn tất cục bộ không tự chứng minh máy chủ đã chấp nhận phiên.

Nền tảng và trách nhiệm tích hợp TLS được mô tả trong [JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html). Khi triển khai cụ thể, phải kiểm tra tài liệu của cơ chế và phiên bản đang sử dụng, không chọn theo ví dụ lịch sử đơn lẻ.

## 10. Ví dụ Java 17+: dùng vừa đủ công cụ cho một yêu cầu nhỏ

Yêu cầu: tạo kế hoạch phân phối hai thông báo qua một tập kênh hữu hạn. Chương trình chỉ tạo dữ liệu kế hoạch; **không gửi email hoặc SMS**.

Lựa chọn thiết kế:

- `List<Notice>` và `List<Delivery>` giữ quan hệ kiểu.
- Một enum biểu diễn kênh; EnumSet biểu diễn nhiều kênh cùng chọn.
- For mở rộng phù hợp thao tác duyệt.
- Dữ liệu trung gian được tạo cục bộ; không cần khóa hoặc executor cho việc lập kế hoạch nhỏ này.
- Record và `List.copyOf()` là API/cú pháp của Java mới hơn, được kết hợp với nền tảng có từ Java 5. Không gọi toàn bộ ví dụ là cú pháp chạy trên JDK 5.

Lưu thành `FeatureChoiceDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.EnumSet;
import java.util.List;
import java.util.Objects;

public class FeatureChoiceDemo {
    enum Channel {
        EMAIL, SMS
    }

    record Notice(String id, String content) {
        Notice {
            Objects.requireNonNull(id);
            Objects.requireNonNull(content);
        }
    }

    record Delivery(String noticeId, Channel channel) {
    }

    static List<Delivery> buildPlan(
            List<Notice> notices, Collection<Channel> requestedChannels) {
        Objects.requireNonNull(notices);
        Objects.requireNonNull(requestedChannels);

        EnumSet<Channel> channels = EnumSet.noneOf(Channel.class);
        channels.addAll(requestedChannels);
        List<Delivery> plan = new ArrayList<>();

        for (Notice notice : notices) {
            Objects.requireNonNull(notice);
            for (Channel channel : channels) {
                plan.add(new Delivery(notice.id(), channel));
            }
        }
        return List.copyOf(plan);
    }

    public static void main(String[] args) {
        List<Notice> notices = List.of(
                new Notice("n1", "Build ready"),
                new Notice("n2", "Report ready"));
        EnumSet<Channel> requested =
                EnumSet.of(Channel.SMS, Channel.EMAIL);

        List<Delivery> plan = buildPlan(notices, requested);
        requested.clear();

        System.out.println("plan=" + plan);
        System.out.println("count=" + plan.size());
        System.out.println("emptyCount="
                + buildPlan(notices, List.of()).size());
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac -Xlint:all -Werror FeatureChoiceDemo.java
java FeatureChoiceDemo
```

Stdout:

```text
plan=[Delivery[noticeId=n1, channel=EMAIL], Delivery[noticeId=n1, channel=SMS], Delivery[noticeId=n2, channel=EMAIL], Delivery[noticeId=n2, channel=SMS]]
count=4
emptyCount=0
```

Những điều được kiểm chứng:

- Kênh được duyệt theo thứ tự khai báo enum, không theo thứ tự truyền vào.
- Tập rỗng được xử lý rõ ràng, không gặp lỗi suy ra kiểu của một collection rỗng.
- Thay đổi tập người gọi giữ sau đó không thay đổi kế hoạch đã tạo.
- Kết quả có kiểu rõ ràng và không cho sửa cấu trúc.

Những điều chưa được kiểm chứng vì không thuộc chương trình này: gửi thật, retry, xác thực dịch vụ gửi, thời hạn I/O và chống gửi trùng. Nếu yêu cầu phát triển tới gửi thông báo thật, các điều kiện đó cần một thiết kế riêng; không chỉ thêm executor quanh vòng lặp rồi coi là hoàn chỉnh.

## 11. Mẫu quyết định ngắn cho một thay đổi thực tế

Có thể ghi lại quyết định theo năm câu:

```text
Yêu cầu:
    Cần diễn tả hay bảo đảm điều gì?

Lựa chọn:
    Dùng tính năng/API nào và tại ranh giới nào?

Hợp đồng:
    Đầu vào, đầu ra, lỗi, quyền sửa và tài nguyên thuộc về ai?

Bằng chứng:
    Compiler, test, ca từ chối hoặc phép đo nào xác nhận?

Điều kiện xem lại:
    Khi tải, dữ liệu, JDK hay yêu cầu nào thay đổi?
```

Ví dụ cho chương trình lập kế hoạch:

- Yêu cầu: nhiều kênh có thể cùng chọn, không chấp nhận một chuỗi kênh tùy ý.
- Lựa chọn: enum và EnumSet, API đầu vào/đầu ra có kiểu.
- Hợp đồng: tập rỗng nghĩa không phân phối; cấu trúc đầu vào không bị sửa; đầu ra tách biệt.
- Bằng chứng: biên dịch sạch, số kế hoạch đúng, ca tập rỗng đúng.
- Điều kiện xem lại: xuất hiện kênh do người dùng định nghĩa hoặc phải gửi qua mạng thật.

Mẫu này giúp nối công cụ với mục tiêu thay vì dùng nó vì đã học qua.

## 12. Những dấu hiệu nên dừng lại và thiết kế lại

| Dấu hiệu | Câu hỏi cần xem lại |
| --- | --- |
| Phải ép kiểu ở nhiều nơi để dùng API generic | Quan hệ kiểu có đang biểu diễn sai không? |
| Có nhiều cờ enum loại trừ lẫn nhau | Đây có thực chất là một chế độ đơn lẻ không? |
| Annotation được thêm nhưng không ai xử lý | Nó có tạo giá trị kiểm tra hay hành vi nào không? |
| Executor tạo ở mỗi yêu cầu và không có chủ sở hữu | Vòng đời và giới hạn tài nguyên ở đâu? |
| Lỗi Future bị bỏ qua | Ai chịu trách nhiệm kết luận công việc thành công? |
| Dùng volatile để bảo vệ một chuỗi thao tác | Có đang cần tính nguyên tử hoặc một khóa cho bất biến không? |
| Cấu hình bảo mật được nới để test chạy | Có đang che lỗi tin cậy/giao thức thay vì giải quyết nguyên nhân không? |
| Tuning không có đường cơ sở | Có dữ liệu để biết thay đổi giúp gì không? |
| Đếm ký tự bằng một đơn vị mơ hồ | Yêu cầu thực sự là byte, code point hay cụm hiển thị? |

Không phải mọi dấu hiệu đều buộc đổi công cụ. Nhưng chúng buộc người thiết kế nói rõ giả định và kiểm tra lại hợp đồng.

## 13. Tự đánh giá sau phần thực hành

Người học nên có thể:

1. Giải thích một API generic ngăn được cách dùng sai nào.
2. Phân biệt một giá trị enum với một tập tùy chọn.
3. Biết annotation nào được compiler/thư viện xử lý và xử lý ở giai đoạn nào.
4. Nhìn thấy rủi ro null và so sánh wrapper khi autoboxing.
5. Chỉ ra ai tạo, sử dụng, hủy và thu lỗi của tác vụ đồng thời.
6. Nêu quan hệ đồng bộ cần thiết khi chia sẻ dữ liệu.
7. Phân biệt đơn vị độ dài văn bản và giữ đúng ranh giới Unicode.
8. Thu bằng chứng runtime để kiểm tra một giả thuyết.
9. Phân biệt API bảo mật với chính sách/cơ chế cụ thể đang triển khai.
10. Chọn một giải pháp đơn giản hơn khi yêu cầu chưa cần công cụ phức tạp.

Câu trả lời tốt không chỉ nêu tên tính năng. Nó phải nối được **yêu cầu → hợp đồng → lựa chọn → bằng chứng → giới hạn**.

# Extreme Programming và vai trò của phản hồi kỹ thuật nhanh

## 1. Một thay đổi nhỏ có thể tạo ra lỗi lớn như thế nào?

Giả sử nhóm phát triển một nền tảng học trực tuyến vừa bổ sung tính năng **đăng ký buổi học có giới hạn số chỗ**. Lập trình viên sửa một điều kiện kiểm tra số chỗ, chạy thử giao diện với dữ liệu mẫu và thấy nút “Đăng ký” hoạt động. Ba ngày sau, khi tích hợp nhiều nhánh mã, nhóm phát hiện học viên vẫn có thể đăng ký vượt sức chứa. Đến lúc bản phát hành được người dùng thử, một lỗi khác xuất hiện: hai yêu cầu đăng ký đến gần như đồng thời đều được xác nhận cho chỗ cuối cùng.

Vấn đề không nhất thiết do người lập trình thiếu năng lực. Một phần nguyên nhân có thể nằm ở **khoảng cách quá lớn giữa lúc thay đổi mã và lúc nhận được bằng chứng rằng thay đổi đó đúng, tích hợp được và an toàn**.

**Extreme Programming (XP)** là cách tiếp cận phát triển phần mềm thuộc họ Agile, nhấn mạnh **cộng tác chặt chẽ, phản hồi nhanh và kỷ luật kỹ thuật** để nhóm có thể thay đổi phần mềm thường xuyên mà vẫn duy trì chất lượng. Chữ “Extreme” không có nghĩa làm việc cực đoan, tăng ca hoặc viết mã nhanh bất chấp rủi ro. Ý tưởng quan trọng là **đưa những thực hành có ích như kiểm thử, rà soát, tích hợp và phản hồi diễn ra sớm và thường xuyên hơn**.

XP đặc biệt chú trọng câu hỏi:

> Khi nhóm thay đổi mã hoặc hiểu biết về yêu cầu, làm thế nào phát hiện sai lệch đủ sớm để còn sửa với chi phí hợp lý?

Đây là nền tảng kỹ thuật quan trọng cho mục tiêu của module **AGILE_DEVELOPMENT**: thích ứng thông qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục. User story và backlog làm rõ giá trị cần tạo; Scrum có thể cung cấp nhịp kiểm tra–thích ứng; Kanban giúp quan sát dòng công việc; XP cung cấp nhiều **thực hành kỹ thuật và cộng tác** giúp mỗi thay đổi được xác minh nhanh và an toàn hơn.

### Kết quả học tập

Sau bài này, người học có thể:

1. Giải thích bản chất XP và vai trò của **phản hồi kỹ thuật nhanh** trong phát triển phần mềm thích ứng.
2. Phân biệt các vòng phản hồi từ mức mã nguồn, tích hợp, hệ thống đến người dùng và production.
3. Thực hành tư duy **Test-Driven Development (TDD)** theo chu trình Red–Green–Refactor.
4. Giải thích sự phối hợp giữa pair programming, simple design, refactoring, collective code ownership, coding standards và continuous integration.
5. Nhận diện giới hạn của phản hồi tự động: kiểm thử xanh không đồng nghĩa sản phẩm đã đúng nhu cầu hoặc an toàn trong mọi tình huống.
6. Đề xuất cách áp dụng XP từng bước và đo xem tốc độ phản hồi có giúp giảm lỗi, thời gian chờ và việc làm lại hay không.

## 2. XP là gì và vì sao chú trọng phản hồi?

XP phát triển trong bối cảnh các nhóm phần mềm cần đáp ứng yêu cầu thay đổi, giảm thời gian từ ý tưởng đến phần mềm hoạt động và giữ mã đủ dễ hiểu để tiếp tục sửa đổi. XP không chỉ là một kỹ thuật viết mã hay một công cụ tự động hóa; nó kết hợp **giá trị, nguyên tắc và các thực hành** về kỹ thuật lẫn sự hợp tác với người hiểu nhu cầu.

Các thực hành thường gắn với XP bao gồm **lập kế hoạch cùng khách hàng, câu chuyện nhỏ, kiểm thử trước hoặc kiểm thử thường xuyên, lập trình cặp, thiết kế đơn giản, tái cấu trúc, tích hợp liên tục, sở hữu mã chung, quy ước mã và nhịp làm việc bền vững**. Những mô tả hoặc phiên bản XP khác nhau có thể nhóm các thực hành theo cách khác nhau; không nên coi một danh sách đếm số thực hành là tiêu chuẩn duy nhất để xác nhận “đã làm XP”.

### 2.1. Năm giá trị thường được nhấn mạnh trong XP

| Giá trị | Ý nghĩa thực hành | Liên hệ với phản hồi nhanh |
|---|---|---|
| **Communication — Giao tiếp** | Thành viên và người hiểu nghiệp vụ cùng làm rõ quy tắc, ví dụ, khó khăn. | Giảm thời gian chờ giải thích và phát hiện hiểu nhầm trước khi mã lan rộng. |
| **Simplicity — Đơn giản** | Chọn thiết kế đủ đáp ứng nhu cầu đang biết, tránh xây khả năng chưa có căn cứ. | Đường kiểm tra ngắn hơn, ít phần phải sửa khi phát hiện sai. |
| **Feedback — Phản hồi** | Dùng kiểm thử, tích hợp, người dùng và hoạt động thực tế để kiểm tra giả định. | Cung cấp bằng chứng sớm về hành vi và chất lượng. |
| **Courage — Can đảm** | Dám sửa thiết kế, chỉ ra lỗi, loại bỏ giải pháp không phù hợp. | Giúp nhóm thực sự điều chỉnh khi bằng chứng trái kỳ vọng. |
| **Respect — Tôn trọng** | Tin tưởng chuyên môn, học hỏi và hỗ trợ nhau; không đổ lỗi khi lỗi được phát hiện. | Thành viên có động lực nêu vấn đề sớm và chia sẻ tri thức. |

Các giá trị hỗ trợ lẫn nhau. Một bộ kiểm thử có thể chạy rất nhanh, nhưng nếu kỹ sư sợ bị trách phạt khi báo lỗi, phản hồi đó sẽ không được sử dụng hiệu quả. Tương tự, sự cởi mở mà thiếu kỹ thuật kiểm chứng có thể dẫn tới nhiều tranh luận nhưng ít bằng chứng.

### 2.2. XP phù hợp với vấn đề nào?

XP đặc biệt hữu ích khi:

- Yêu cầu nghiệp vụ cần được làm rõ dần và có thể thay đổi qua phản hồi.
- Phần mềm được thay đổi thường xuyên, khiến lỗi hồi quy dễ xuất hiện.
- Nhóm cần phát hành theo phần nhỏ nhưng vẫn bảo vệ chất lượng.
- Nhiều lập trình viên cùng tác động đến một codebase và cần tránh tích hợp muộn.
- Kiến thức nghiệp vụ hoặc kỹ thuật đang tập trung ở ít người.
- Chi phí sửa lỗi tăng mạnh khi phát hiện muộn.

XP không loại bỏ nhu cầu về kiến trúc, an toàn, nghiên cứu hoặc kế hoạch. Nó giúp nhóm **đưa những quyết định đó vào các vòng kiểm tra ngắn hơn**, thay vì tin rằng một tài liệu thiết kế ban đầu đủ bảo đảm phần mềm sẽ đúng trong mọi tình huống.

## 3. Phản hồi kỹ thuật nhanh là gì?

**Phản hồi kỹ thuật (technical feedback)** là thông tin về tính đúng đắn, khả năng tích hợp, chất lượng và độ an toàn của một thay đổi phần mềm. Phản hồi có thể đến từ trình biên dịch, bài kiểm thử, một lập trình viên cùng làm, quy trình tích hợp, môi trường thử hoặc hệ thống đang vận hành.

**Nhanh** không chỉ là một con số mili giây. Giá trị của phản hồi phụ thuộc vào ba yếu tố:

1. **Độ trễ:** sau bao lâu nhóm mới biết một giả định hoặc thay đổi có vấn đề?
2. **Độ tin cậy:** tín hiệu có chính xác, ổn định và phản ánh rủi ro cần quan tâm không?
3. **Khả năng hành động:** kết quả có đủ rõ để biết nơi cần điều tra, sửa hoặc đổi hướng không?

Một bài kiểm thử chạy trong một giây nhưng thường thất bại ngẫu nhiên có thể ít hữu ích hơn bài kiểm thử mất hai phút nhưng phát hiện lỗi đáng tin và chỉ rõ nguyên nhân. Tối ưu XP không phải **biến mọi tín hiệu thành nhanh nhất bằng mọi giá**, mà là tạo vòng phản hồi **sớm, có ý nghĩa và đủ tin cậy**.

### 3.1. Độ trễ phản hồi làm tăng phạm vi phải điều tra

Khi một thay đổi gây lỗi nhưng chỉ bị phát hiện sau khi thêm hàng chục thay đổi khác, nhóm phải xem một không gian nguyên nhân lớn hơn. Họ có thể cần dựng lại trạng thái cũ, đọc nhiều commit, hỏi nhiều người hoặc tái hiện dữ liệu đã thay đổi.

Ngược lại, nếu lỗi được phát hiện ngay sau một thay đổi nhỏ:

- Phạm vi mã cần kiểm tra thường hẹp hơn.
- Ngữ cảnh của người sửa còn mới.
- Có thể điều chỉnh trước khi người khác xây dựa trên giả định sai.
- Kiểm tra hồi quy giúp giảm nguy cơ lỗi tái xuất hiện.
- Nhóm có thể giữ cho mã ở trạng thái thay đổi được mà ít lo sợ hơn.

Đây là lý do XP khuyến khích **thay đổi nhỏ, kiểm tra thường xuyên và tích hợp liên tục**.

### 3.2. Các vòng phản hồi lồng vào nhau

~~~mermaid
flowchart TD
    A["Thay đổi nhỏ trong mã"] --> B["Biên dịch, lint, unit tests"]
    B --> C["Phản hồi từ lập trình cặp / rà soát"]
    C --> D["Tích hợp chung và contract/integration tests"]
    D --> E["Kiểm tra luồng sản phẩm / acceptance tests"]
    E --> F["Increment dùng được và phản hồi người dùng"]
    F --> G["Quan sát vận hành, điều chỉnh backlog"]
    G --> A
    B -->|Lỗi| A
    D -->|Sai lệch| A
    E -->|Chưa đáp ứng| A
~~~

Sơ đồ đơn giản hóa dòng công việc: các vòng không nhất thiết chạy một lần theo đúng thứ tự trên. Lập trình cặp phản hồi **ngay khi viết mã**; unit test có thể chạy liên tục; CI chạy mỗi lần tích hợp; kiểm thử khám phá có thể xen vào giữa; phản hồi người dùng có thể đến trước hoặc sau phát hành giới hạn.

**Vòng ngắn hỗ trợ vòng dài**, nhưng không thay thế nó. Unit test xanh chưa chứng minh chức năng có giá trị; người dùng thích giao diện chưa chứng minh dữ liệu được bảo vệ.

## 4. Chọn loại phản hồi theo câu hỏi cần trả lời

| Vòng phản hồi | Câu hỏi chính | Thời điểm mong muốn | Giới hạn |
|---|---|---|---|
| **Compiler, type check, static analysis** | Mã có hợp lệ về cú pháp, kiểu và quy tắc tĩnh không? | Rất sớm, ngay khi thay đổi. | Không chứng minh hành vi nghiệp vụ đúng. |
| **Unit test** | Một đơn vị logic có xử lý các ví dụ, ranh giới và trường hợp lỗi đã biết không? | Thường xuyên trong lúc viết mã. | Có thể bỏ sót tích hợp, cạnh tranh và hiểu sai yêu cầu. |
| **Pair programming / trao đổi trực tiếp** | Thiết kế, giả định và hướng sửa có hợp lý không? | Ngay trong quá trình làm. | Hai người vẫn có thể cùng hiểu sai nghiệp vụ. |
| **Contract test** | Những bên giao tiếp có tuân theo hợp đồng API/sự kiện không? | Khi hợp đồng hoặc mã liên quan thay đổi. | Không kiểm chứng toàn bộ quy trình nghiệp vụ. |
| **Integration test** | Những thành phần có hoạt động đúng khi kết nối? | Càng sớm càng tốt, lặp lại theo rủi ro. | Môi trường thử có thể khác production. |
| **Acceptance/example-based test** | Hành vi quan sát được có đáp ứng ví dụ và quy tắc nghiệp vụ? | Trong lúc phát triển và trước khi coi hạng mục hoàn thành. | Các ví dụ đã viết có thể thiếu trường hợp chưa nghĩ tới. |
| **Exploratory testing** | Có rủi ro, hành vi bất ngờ hoặc mâu thuẫn nào chưa được đặc tả? | Xen kẽ khi có Increment đáng kiểm tra. | Khó bao phủ mọi tình huống; cần ghi phát hiện và học hỏi. |
| **Phản hồi người dùng / stakeholder** | Giải pháp có giải quyết đúng nhu cầu và tạo giá trị không? | Với phần giá trị đủ nhỏ, an toàn để đánh giá. | Phản hồi có thể thiên lệch; cần bối cảnh và phương pháp phù hợp. |
| **Quan sát production** | Hệ thống hoạt động thế nào trong môi trường thực tế? | Sau khi mở sử dụng, theo dõi liên tục khi cần. | Không được lấy production làm nơi thử những rủi ro an toàn chưa kiểm soát. |

### 4.1. Phản hồi nhanh không chỉ là kiểm thử tự động

Người nghiệp vụ xác nhận một ví dụ trước khi lập trình cũng là phản hồi nhanh. Một lập trình viên khác nhận ra lỗ hổng phân quyền trong buổi pair programming cũng là phản hồi nhanh. Việc hỏi người dùng ngay khi một lát tính năng dùng được có thể giúp tránh hàng tuần xây thêm các phần họ không cần.

**Kỷ luật kỹ thuật tạo cơ hội học hỏi nhanh**, nhưng nhóm còn cần kỹ năng giao tiếp, làm rõ giá trị và quyết định dựa trên bằng chứng.

### 4.2. Phản hồi đúng nhưng đến muộn vẫn gây lãng phí

Nếu nhóm chỉ chạy kiểm thử tích hợp vào cuối tháng, thông báo lỗi lúc đó có thể hoàn toàn chính xác nhưng đã đến sau nhiều thay đổi liên quan. XP thường tìm cách **dịch chuyển phát hiện lỗi về sớm**, ví dụ qua kiểm tra hợp đồng, tích hợp thường xuyên và dữ liệu thử đại diện.

Không phải mọi bài kiểm thử cần chạy sau từng lần gõ phím. Nhóm có thể chia bộ kiểm tra thành **vòng rất nhanh** khi sửa mã và **vòng sâu hơn** theo commit, tích hợp hoặc lịch thích hợp, miễn là không tạo ra khoảng trống rủi ro khó chấp nhận.

## 5. TDD: tạo vòng phản hồi Red–Green–Refactor

**Test-Driven Development (TDD)** là thực hành thiết kế và phát triển bằng cách viết một kiểm thử tự động nhỏ **trước khi** viết phần mã sản xuất đáp ứng hành vi đó. Chu trình thường được mô tả:

1. **Red:** viết một kiểm thử thể hiện hành vi mong muốn và quan sát nó thất bại vì hành vi chưa có hoặc chưa đúng.
2. **Green:** viết lượng mã đủ để kiểm thử vượt qua, không mở rộng không cần thiết.
3. **Refactor:** cải thiện cấu trúc mã trong khi giữ các kiểm thử đạt, qua đó bảo toàn hành vi đã được xác nhận.

~~~mermaid
flowchart LR
    A["Red: viết một kiểm thử thất bại đúng lý do"] --> B["Green: viết mã tối thiểu để qua kiểm thử"]
    B --> C["Refactor: cải thiện cấu trúc, giữ hành vi"]
    C --> D["Chọn một ví dụ mới hoặc ranh giới mới"]
    D --> A
~~~

Mỗi vòng nên đủ nhỏ để khi kiểm thử thất bại, người phát triển có thể xác định nguyên nhân với ít công sức. TDD không có nghĩa viết hàng trăm bài kiểm thử trước khi xây bất kỳ mã nào.

### 5.1. Ví dụ Java: kiểm tra còn chỗ đăng ký

Giả sử quy tắc nghiệp vụ đã được làm rõ:

> Một buổi học cho phép thêm một người đăng ký nếu sức chứa dương, số người đã đăng ký không âm và còn ít nhất một chỗ.

Đầu tiên, người phát triển viết các kiểm thử **JUnit 5** cho một thành phần logic nhỏ:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class SeatPolicyTest {

    @Test
    void allowsBookingWhenSeatsRemain() {
        assertTrue(SeatPolicy.canBook(10, 9));
    }

    @Test
    void rejectsBookingWhenFull() {
        assertFalse(SeatPolicy.canBook(10, 10));
    }

    @Test
    void rejectsInvalidInput() {
        assertFalse(SeatPolicy.canBook(0, 0));
        assertFalse(SeatPolicy.canBook(10, -1));
        assertFalse(SeatPolicy.canBook(10, 11));
    }
}
~~~

Trong bước **Red**, lớp **SeatPolicy** chưa có hoặc chưa triển khai hành vi nên kiểm thử không thành công. Trong thực hành TDD, điều quan trọng là kiểm tra thất bại có **đúng lý do mong đợi** hay không; lỗi thiếu dependency, cấu hình build hỏng hoặc cú pháp sai không phải bằng chứng một quy tắc nghiệp vụ chưa được đáp ứng.

Ở bước **Green**, có thể bắt đầu với mã đơn giản:

~~~java
public final class SeatPolicy {

    private SeatPolicy() {
    }

    public static boolean canBook(int capacity, int booked) {
        return capacity > 0
                && booked >= 0
                && booked < capacity;
    }
}
~~~

Chạy lại kiểm thử để xác nhận các ví dụ đã qua. Sau đó ở bước **Refactor**, người phát triển cân nhắc tên hàm, độ dễ hiểu, cấu trúc và việc loại bỏ lặp. Với đoạn mã nhỏ trên, có thể **không cần refactor gì thêm**; không nên tạo abstraction mới chỉ để chứng minh đã thực hiện bước Refactor.

Một vòng tiếp theo có thể bổ sung quy tắc mới, chẳng hạn buổi học đã bị hủy thì không cho đăng ký dù còn chỗ. Khi đó nhóm cần làm rõ trạng thái nghiệp vụ, viết kiểm thử cho tình huống mới rồi mở rộng thiết kế có kiểm chứng.

### 5.2. Điều mà ví dụ unit test chưa chứng minh

Các kiểm thử trên chỉ kiểm tra một **hàm thuần** với dữ liệu được truyền vào. Chúng **không chứng minh rằng hệ thống thực tế sẽ không bao giờ đăng ký vượt sức chứa**.

Giả sử buổi học chỉ còn một chỗ, hai yêu cầu đồng thời đều đọc **booked = 9, capacity = 10**. Cả hai cùng gọi **canBook(10, 9)** và nhận **true**. Nếu mỗi yêu cầu sau đó tự ghi đăng ký mà không có kiểm soát cạnh tranh, số người đăng ký có thể lên 11.

Để bảo vệ bất biến “không vượt sức chứa”, hệ thống còn cần một cơ chế ghi **nguyên tử/nhất quán theo kiến trúc** (ví dụ điều kiện cập nhật tại cơ sở dữ liệu, khóa hoặc phương án điều phối phù hợp) và kiểm thử tích hợp/tình huống đồng thời. Cơ chế cụ thể phụ thuộc hệ thống và phải được chứng minh bằng kiểm tra thích hợp.

Đây là bài học quan trọng: **TDD cho phản hồi rất nhanh về một mức hành vi, nhưng không loại bỏ nhu cầu kiểm chứng ở các mức khác**.

### 5.3. TDD khác “viết test sau khi xong code”

| Cách làm | Điểm mạnh | Rủi ro nếu chỉ dựa vào cách đó |
|---|---|---|
| **TDD với vòng nhỏ** | Kiểm thử dẫn dắt hành vi và thiết kế; phản hồi ngay khi thay đổi. | Kiểm thử có thể quá bám cấu trúc nội bộ hoặc bỏ sót rủi ro hệ thống. |
| **Viết test sau khi có mã** | Vẫn có thể bổ sung bảo vệ hồi quy và chứng minh các trường hợp đã biết. | Dễ bỏ qua các trường hợp mà thiết kế hiện tại chưa hỗ trợ; phản hồi đến muộn. |
| **Chỉ kiểm thử thủ công cuối đợt** | Có thể phát hiện lỗi trải nghiệm và hành vi khó tự động hóa. | Chậm, lặp lại tốn sức và bỏ sót hồi quy giữa những lần thay đổi. |

TDD không phải bảo đảm tuyệt đối rằng thiết kế tốt hoặc hết lỗi. Nhóm vẫn cần kiểm tra giả định nghiệp vụ, quyền truy cập, dữ liệu, khả năng phục hồi và chất lượng sản phẩm thực.

## 6. Pair Programming: phản hồi trong lúc suy nghĩ và viết mã

**Pair programming (lập trình cặp)** là thực hành hai người cùng cộng tác trên một công việc lập trình tại cùng thời điểm. Thường mô tả hai góc nhìn:

- **Driver** trực tiếp thao tác với mã, kiểm thử và công cụ.
- **Navigator** quan sát hướng giải quyết, đặt câu hỏi về thiết kế, trường hợp biên và bước tiếp theo.

Hai người có thể đổi vai trò thường xuyên. Mục đích không phải để một người làm còn người kia chỉ giám sát hoặc đánh giá năng suất. Họ **cùng chịu trách nhiệm với lời giải**, dùng sự khác biệt về góc nhìn để phát hiện sai lệch sớm.

### 6.1. Những phản hồi có thể nhận ngay trong một phiên pair

Giả sử một người đang triển khai xử lý đăng ký buổi học:

- Người thứ hai hỏi: “Nếu khách nhấn gửi hai lần thì có tạo hai đăng ký không?”
- Người viết mã nhận thấy logic kiểm tra chỗ trống đang đặt ở frontend thay vì nơi ghi dữ liệu.
- Hai người quyết định viết trước kiểm thử cho trạng thái đầy và trường hợp nhập dữ liệu không hợp lệ.
- Khi test qua, họ cùng thảo luận xem tên hàm có diễn đạt đúng quy tắc không.
- Họ ghi câu hỏi chưa rõ về danh sách chờ để hỏi người nghiệp vụ.

Những quyết định này có thể xảy ra trước khi một pull request lớn được gửi đi, giúp giảm thời gian chờ phản hồi và chi phí giải thích ngữ cảnh.

### 6.2. Pair không có nghĩa mọi thay đổi đều cần đúng hai người

Lập trình cặp có thể đặc biệt có ích khi:

- Thay đổi liên quan logic phức tạp, tiền, quyền truy cập hoặc dữ liệu quan trọng.
- Một thành viên cần học một phần codebase chưa quen.
- Cần cân nhắc thiết kế có nhiều lựa chọn.
- Có lỗi khó tái hiện hoặc khẩn cấp cần điều tra phối hợp.
- Tri thức đang tập trung ở một người.

Với thay đổi nhỏ, rõ ràng, nhóm có thể chọn cách cộng tác khác như kiểm thử tự động, trao đổi ngắn hoặc rà soát mã. **XP coi cộng tác là công cụ giúp chất lượng và học hỏi, không phải nghi thức bắt buộc phải thực hiện máy móc trong mọi phút làm việc**.

### 6.3. Phản hồi kỹ thuật cần sự tôn trọng

Một phiên pair thất bại nếu thành viên giàu kinh nghiệm chỉ ra lệnh, người còn lại không có cơ hội giải thích hoặc mọi nhận xét đều biến thành phê bình cá nhân. Nên thống nhất:

1. Mục tiêu và phạm vi thay đổi.
2. Cách đổi vai trò và đặt câu hỏi.
3. Khi nào cần dừng để làm rõ yêu cầu.
4. Điều kiện kiểm chứng trước khi coi công việc xong.
5. Cách ghi quyết định quan trọng cho những người không tham gia phiên pair.

Lợi ích lớn không chỉ là “ít bug hơn”, mà còn là **kiến thức có thể chia sẻ và khả năng sửa đổi mã không lệ thuộc duy nhất vào một người**.

## 7. Continuous Integration: phản hồi nhanh về khả năng ghép các thay đổi

**Continuous Integration (CI)** là thực hành tích hợp các thay đổi mã vào nhánh chung thường xuyên, với quy trình xây dựng và kiểm tra tự động phù hợp nhằm phát hiện xung đột sớm. Trong XP, CI bổ sung cho những vòng TDD và pair programming ở mức cục bộ.

Nếu mỗi người làm việc trên một nhánh tách biệt trong nhiều tuần, mọi kiểm thử cục bộ có thể xanh nhưng hệ thống chung vẫn không tích hợp được. Hai nhóm có thể cùng thay đổi hợp đồng API hoặc cấu trúc dữ liệu theo giả định khác nhau.

### 7.1. Quy trình phản hồi CI minh họa

~~~text
Thay đổi nhỏ
  -> chạy kiểm tra nhanh tại máy phát triển
  -> tích hợp với nhánh chung
  -> build + unit tests + kiểm tra tĩnh
  -> contract/integration tests theo rủi ro
  -> kiểm tra lỗi và sửa khi kết quả không đạt
  -> tạo trạng thái chung đáng tin cậy cho thay đổi tiếp theo
~~~

Không có một thời lượng pipeline hay danh sách công cụ bắt buộc cho tất cả dự án. Điều quan trọng là **thời gian chờ phản hồi đủ ngắn để thành viên sử dụng được kết quả trong lúc ngữ cảnh còn mới**, đồng thời giữ tín hiệu chất lượng cần thiết.

### 7.2. Một pipeline kiểm tra theo nhiều mức

| Nhóm kiểm tra | Ví dụ | Mục đích |
|---|---|---|
| **Kiểm tra rất nhanh** | Biên dịch, kiểm tra định dạng, unit tests cốt lõi. | Phát hiện lỗi rõ ràng ngay sau thay đổi. |
| **Kiểm tra tương tác** | API contract, tích hợp cơ sở dữ liệu, kịch bản lỗi quan trọng. | Phát hiện bất đồng giữa các thành phần. |
| **Kiểm tra luồng sản phẩm** | Đăng ký buổi học từ giao diện đến ghi nhận chỗ, kiểm tra phân quyền. | Xác minh hành vi xuyên hệ thống theo ví dụ có giá trị. |
| **Kiểm tra sâu theo lịch/rủi ro** | Tải, bảo mật chuyên sâu, tương thích hệ thống ngoài. | Phát hiện các rủi ro không phù hợp chạy liên tục ở mọi thay đổi. |

Nhóm có thể tối ưu thứ tự chạy để nhận lỗi phổ biến sớm. Tuy nhiên, **không được bỏ các kiểm soát bắt buộc chỉ để pipeline chạy nhanh hoặc giữ trạng thái xanh**.

### 7.3. Khi pipeline đỏ, phản hồi phải có hành động

CI chỉ có giá trị nếu nhóm **xử lý tín hiệu**, không để nhánh tích hợp hỏng kéo dài. Một quy tắc cộng tác hữu ích là:

- Khi kiểm tra chung thất bại, xác nhận nguyên nhân trước khi tích hợp thêm thay đổi có nguy cơ làm tình hình khó hiểu.
- Người có khả năng liên quan phối hợp sửa hoặc hoàn tác an toàn thay đổi gây lỗi.
- Nếu test thất bại ngẫu nhiên, ghi nhận và xử lý **flaky test**; không coi việc chạy lại cho đến khi xanh là bằng chứng không còn vấn đề.
- Minh bạch những bộ kiểm tra chưa được chạy hoặc đang không đáng tin.
- Sau khi sửa, xác minh ở những mức chịu tác động để bảo đảm lỗi đã được xử lý.

Đây là cách giữ **trạng thái chung của codebase đáng tin**, giúp các vòng phản hồi tiếp theo tiếp tục có ý nghĩa.

### 7.4. CI không đồng nghĩa Continuous Deployment

CI nói về **tích hợp và xác minh thay đổi thường xuyên**. **Continuous Delivery** liên quan khả năng chuẩn bị phần mềm sẵn sàng để phát hành thường xuyên, còn **Continuous Deployment** là tự động đưa thay đổi đủ điều kiện đến môi trường sử dụng theo chính sách.

Nhóm có thể thực hành CI rất tốt nhưng vẫn có quyết định phát hành có kiểm soát do rủi ro, nghĩa vụ pháp lý hoặc chiến lược sản phẩm. Đừng đánh đồng “merge thành công”, “CI xanh”, “Increment đạt Done” và “đã phát hành”.

## 8. Simple Design và Refactoring: làm cho thay đổi tiếp theo an toàn hơn

**Simple design (thiết kế đơn giản)** trong XP nhấn mạnh giải pháp đủ đáp ứng nhu cầu đang biết và dễ hiểu đối với người cần thay đổi nó. Nó không đồng nghĩa viết mã ngắn nhất bằng mọi cách, bỏ xử lý lỗi hoặc từ chối kiến trúc cần thiết.

**Refactoring (tái cấu trúc)** là thay đổi cấu trúc bên trong phần mềm **mà không chủ ý thay đổi hành vi quan sát được**. Các kiểm thử đáng tin cung cấp phản hồi giúp người phát triển tự tin rằng hành vi cũ vẫn được giữ.

### 8.1. Phân biệt ba loại thay đổi

| Loại | Mục tiêu | Ví dụ |
|---|---|---|
| **Bổ sung hành vi** | Cung cấp một khả năng hoặc quy tắc mới. | Không cho học viên đăng ký buổi học đã bị hủy. |
| **Sửa lỗi** | Khôi phục hành vi đúng theo mong đợi. | Ngăn hệ thống xác nhận hai người cho cùng một chỗ cuối. |
| **Refactoring** | Cải thiện thiết kế nhưng giữ hành vi đã thống nhất. | Trích xuất quy tắc tính chỗ trống từ một phương thức dài, không đổi kết quả hợp lệ. |

Trên thực tế một hạng mục lớn có thể chứa cả ba, nhưng nên **tách các bước đủ nhỏ để biết thay đổi nào làm hỏng kiểm thử**.

### 8.2. Vì sao refactoring cần diễn ra thường xuyên?

Khi nhóm liên tục thêm quy tắc nhưng không cải thiện thiết kế, mã có thể tích tụ:

- Trùng lặp logic ở nhiều màn hình và API.
- Tên biến/hàm không còn phản ánh ý nghĩa nghiệp vụ.
- Các thành phần phụ thuộc chặt, khiến sửa một nơi ảnh hưởng nhiều nơi.
- Kiểm thử khó viết do hành vi trộn với kết nối hệ thống hoặc trạng thái toàn cục.

Những vấn đề này làm vòng phản hồi tương lai chậm hơn. **Refactoring nhỏ, có kiểm chứng** giúp giảm chi phí thay đổi và giữ codebase đủ dễ hiểu để phát triển liên tục.

### 8.3. Đừng đồng nhất “đơn giản” với “thiếu an toàn”

Ví dụ, dùng một phép kiểm tra **booked < capacity** trước khi ghi dữ liệu có vẻ đơn giản, nhưng không đủ nếu nhiều người đăng ký đồng thời. Để bảo toàn số chỗ, thiết kế cần cơ chế đồng bộ/ghi nguyên tử phù hợp. Độ phức tạp này **có lý do từ yêu cầu thật**, không phải thiết kế quá mức.

Ngược lại, xây ngay một nền tảng đặt chỗ hỗ trợ hàng chục nhà cung cấp, mô hình đa trung tâm và chiến lược cache chưa có nhu cầu có thể làm tăng chi phí phản hồi mà chưa tạo giá trị tương ứng.

**Thiết kế đơn giản là giải pháp đơn giản nhất còn đáp ứng những ràng buộc thật, bao gồm chất lượng và an toàn.**

## 9. Collective Code Ownership và Coding Standards

Trong XP, **collective code ownership (sở hữu mã chung)** giúp những người có năng lực phù hợp có thể cải thiện phần mã cần thiết thay vì mọi thay đổi đều phải chờ “chủ sở hữu” của một tệp.

Điều này có lợi khi:

- Một lỗi liên quan nhiều module cần được sửa nhanh.
- Một người vắng mặt nhưng kiến thức và kiểm thử đủ để người khác tiếp tục.
- Nhóm muốn cải tiến thiết kế xuyên qua các phần của hệ thống.
- Cần giảm thời gian chờ phê duyệt hoặc chuyển giao chỉ vì ranh giới cá nhân.

Tuy nhiên, sở hữu mã chung **không có nghĩa ai cũng sửa mà không hiểu, bỏ qua review hoặc vượt quyền truy cập bắt buộc**. Nhóm cần kiểm thử, tiêu chuẩn chất lượng, cơ chế phối hợp và quy trình kiểm soát thay đổi phù hợp.

### 9.1. Coding standards tạo phản hồi dễ hiểu

**Coding standards (quy ước mã)** giúp các thành viên đọc và sửa mã của nhau với ít ma sát:

- Cách đặt tên và tổ chức mã thống nhất.
- Định dạng và cấu trúc dễ nhận biết.
- Quy tắc xử lý lỗi, ghi log và dữ liệu nhạy cảm rõ ràng.
- Thực hành kiểm thử và đặt tên kiểm thử nhất quán.
- Cách đưa thay đổi vào nhánh chung và xử lý pipeline thất bại được đồng thuận.

Tự động định dạng hoặc kiểm tra tĩnh có thể giảm tranh luận về những khác biệt cơ học, để buổi review tập trung vào **hành vi, thiết kế và rủi ro**.

### 9.2. Chia sẻ tri thức là một cơ chế giảm rủi ro

Giả sử chỉ một kỹ sư biết cách xử lý webhook của cổng thanh toán. Mỗi lần người đó nghỉ phép, cả nhóm phải chờ. Pair programming, ghi chú quyết định thiết yếu, bộ kiểm thử đáng tin và sở hữu mã chung giúp kỹ sư khác học cách sửa phần liên quan mà không phải đoán mò.

Mục tiêu không phải ai cũng thành chuyên gia mọi thành phần ngay lập tức, mà là **giảm nút thắt thông tin và tăng khả năng phục hồi của nhóm**.

## 10. Small Releases và phản hồi từ khách hàng

XP không chỉ khuyến khích kiểm thử mã nhanh. Một ý tưởng có thể được thực hiện hoàn hảo về kỹ thuật nhưng **không giải quyết đúng vấn đề người dùng**. Vì thế, XP còn đề cao các vòng phản hồi nghiệp vụ như:

- **User stories nhỏ** để thảo luận điều người dùng muốn đạt.
- **Lập kế hoạch cùng người hiểu sản phẩm** nhằm cân bằng giá trị, rủi ro và chi phí.
- **Acceptance tests / customer tests** để có ví dụ rõ về hành vi cần đáp ứng.
- **Small releases** để người dùng hoặc stakeholder có thể xem kết quả thật thường xuyên.
- **Trao đổi liên tục** khi xuất hiện câu hỏi hoặc hiểu biết mới.

Trong mô tả XP truyền thống, “customer” gần nhóm hoặc có khả năng trả lời thường xuyên là một thực hành quan trọng. Trong tổ chức hiện đại, người này có thể là Product Owner, đại diện nghiệp vụ hoặc nhóm người dùng phù hợp, làm việc trực tiếp hay từ xa. Quan trọng là **có đường đưa quyết định và phản hồi kịp thời**, không phải nhất thiết ngồi cùng một phòng.

### 10.1. Kỹ thuật nhanh chưa chắc phản hồi về giá trị nhanh

Ví dụ, bộ test cho việc gửi email xác nhận đăng ký đều xanh, nhưng học viên vẫn không biết mình cần chuẩn bị gì trước buổi học. Nguyên nhân có thể là nội dung email thiếu hướng dẫn, ngôn ngữ khó hiểu hoặc thông báo gửi vào thời điểm không phù hợp.

Nhóm cần kết hợp:

- **Kiểm thử kỹ thuật:** email được tạo một lần cho đăng ký hợp lệ, không gửi cho giao dịch thất bại, không làm lộ dữ liệu.
- **Tiêu chí nghiệp vụ:** email nêu đúng thời gian, đường dẫn và thông tin cần thiết.
- **Kiểm tra trải nghiệm:** học viên thực sự nhận ra và sử dụng thông tin.

Kết quả cần cả **đúng về kỹ thuật** và **có ích cho người dùng**.

### 10.2. Nhỏ về phạm vi, đầy đủ về chất lượng

Small release không có nghĩa phát hành một luồng thanh toán nửa vời hoặc để dữ liệu cá nhân thiếu bảo vệ. Nhóm cần chia **lát giá trị dọc** có thể dùng được trong phạm vi phù hợp và đáp ứng tiêu chuẩn chất lượng liên quan.

Nếu đang xây đăng ký buổi học, lát đầu có thể chỉ hỗ trợ đăng ký một buổi tại một cơ sở nhưng phải xử lý đúng sức chứa, quyền truy cập, lỗi ghi dữ liệu và thông báo trong phạm vi đó. Thêm nhiều loại buổi học là phần phát triển tiếp theo, không phải lý do để bỏ qua lỗi nghiêm trọng của lát đầu.

## 11. Tình huống xuyên suốt: phát triển luồng đăng ký buổi học

**Tình huống và số liệu ở phần này là giả định**, dùng để minh họa cách kết hợp các vòng phản hồi XP. Đây không phải đặc tả sản phẩm hay bằng chứng thực nghiệm.

### 11.1. Bối cảnh và mục tiêu

Một nhóm phát triển nền tảng học lập trình muốn cho học viên đăng ký những buổi hướng dẫn trực tuyến có giới hạn chỗ. Nhóm đang gặp ba khó khăn:

1. Yêu cầu thường được giải thích khác nhau giữa nghiệp vụ, backend và giao diện.
2. Các nhánh mã được tích hợp muộn; lỗi giao tiếp API chỉ xuất hiện gần ngày phát hành.
3. Khi sửa một quy tắc, nhóm lo làm hỏng chức năng cũ nên trì hoãn thay đổi.

Mục tiêu sản phẩm là **học viên đăng ký được buổi phù hợp và biết chắc trạng thái đăng ký**. Nhóm không bắt đầu bằng yêu cầu xây nền tảng đặt chỗ phức tạp cho mọi loại sự kiện.

### 11.2. Làm rõ story và ví dụ trước khi lập trình

User story:

> Với vai trò là học viên muốn tham gia buổi hướng dẫn, tôi muốn đăng ký một chỗ còn trống để có thể tham dự mà không phải liên hệ người tổ chức.

Qua trao đổi giữa người hiểu nghiệp vụ, người phát triển và người kiểm thử, nhóm thống nhất các quy tắc minh họa:

| Quy tắc | Ví dụ cần xác minh |
|---|---|
| Chỉ buổi còn nhận đăng ký mới cho phép đặt. | Buổi đã hủy hoặc đóng đăng ký phải từ chối. |
| Không vượt quá sức chứa. | Hai người cùng đăng ký chỗ cuối không được tạo hai kết quả thành công. |
| Mỗi học viên không được tạo đăng ký trùng khi gửi lại cùng yêu cầu. | Một yêu cầu gửi lặp không tạo thêm bản ghi. |
| Trả trạng thái chính xác. | Lưu thất bại không được hiển thị “đăng ký thành công”. |
| Tôn trọng quyền truy cập. | Người dùng không được chỉnh sửa đăng ký của tài khoản khác. |
| Học viên nhận thông tin xác nhận sau khi đăng ký được ghi nhận. | Không gửi xác nhận cho một thao tác chưa thành công. |

Những quy tắc này trở thành **Conversation và Confirmation** của story, cung cấp đầu vào cho TDD, kiểm thử tích hợp và acceptance tests. Một số câu hỏi còn mở, chẳng hạn danh sách chờ hay hủy sát giờ, có thể được đưa vào backlog nếu ngoài phạm vi lát đầu và không ảnh hưởng an toàn của phần hiện tại.

### 11.3. Các vòng phản hồi trong một lát công việc

| Bước | Thực hành XP | Phản hồi được nhận |
|---|---|---|
| Làm rõ quy tắc | Trao đổi ví dụ với người hiểu sản phẩm. | Phát hiện yêu cầu thiếu hoặc mâu thuẫn trước khi viết mã. |
| Xây logic kiểm tra chỗ | TDD Red–Green–Refactor. | Biết nhanh quy tắc đơn vị có đúng với ví dụ đã thống nhất. |
| Xử lý ghi đăng ký | Pair programming và kiểm thử trạng thái đồng thời. | Nhận ra rủi ro tranh chấp chỗ, cần bảo vệ bất biến dữ liệu. |
| Nối giao diện và API | CI, kiểm thử hợp đồng, tích hợp sớm. | Phát hiện lệch trạng thái/mã lỗi trước khi quá nhiều mã phụ thuộc. |
| Xem luồng người học | Acceptance tests và kiểm thử khám phá. | Kiểm tra các trường hợp người dùng thấy và các hành vi chưa dự kiến. |
| Mở thử giới hạn | Small release với điều kiện an toàn. | Quan sát người dùng có đăng ký được, có hiểu trạng thái và có gặp khó khăn không. |
| Cải tiến sau phản hồi | Refactoring, ưu tiên backlog và bổ sung kiểm thử. | Giảm lỗi lặp lại và chi phí thay đổi phần tiếp theo. |

Nhóm không buộc phải hoàn thành mọi bước theo kiểu bàn giao tuần tự; chúng là **các vòng phản hồi phối hợp và chồng lấp**, diễn ra thường xuyên trong lúc tạo ra Increment.

### 11.4. Một lỗi được phát hiện sớm có giá trị ra sao?

Giả sử ở buổi pair programming, người quan sát hỏi về hai học viên cùng chọn chỗ cuối. Unit test hiện tại chỉ kiểm tra hàm **canBook**. Nhóm quyết định viết thêm kiểm thử tích hợp với hai yêu cầu gần đồng thời, phát hiện cả hai yêu cầu đều thành công.

Nhờ phát hiện trước khi phát hành:

- Chưa có học viên thật bị xác nhận vượt sức chứa.
- Có thể sửa cơ chế ghi và xác minh ngay khi ngữ cảnh còn mới.
- Bộ kiểm thử mới bảo vệ lỗi hồi quy khi mã thay đổi về sau.
- Product Owner biết phần đăng ký chưa đủ an toàn để mở, tránh nhầm “unit test xanh” với “đủ chất lượng”.

**Giá trị của phản hồi nhanh không phải vì nhóm không bao giờ mắc lỗi, mà vì nhóm giảm thời gian lỗi tồn tại và chi phí sửa chữa.**

### 11.5. Bổ sung acceptance test từ góc nhìn người dùng

Ví dụ Given–When–Then:

~~~gherkin
Feature: Đăng ký buổi hướng dẫn

  Scenario: Học viên đăng ký thành công khi còn chỗ
    Given một buổi hướng dẫn đang mở và còn chỗ
    And học viên có quyền đăng ký buổi đó
    When học viên gửi yêu cầu đăng ký hợp lệ
    Then hệ thống ghi nhận đúng một đăng ký
    And học viên thấy trạng thái đăng ký thành công

  Scenario: Không xác nhận vượt sức chứa
    Given buổi hướng dẫn chỉ còn một chỗ trống
    When hai học viên gửi yêu cầu đăng ký gần đồng thời
    Then số đăng ký thành công không vượt sức chứa
    And yêu cầu không được chấp nhận nhận kết quả phù hợp

  Scenario: Yêu cầu gửi lặp
    Given học viên đã có đăng ký hợp lệ cho buổi hướng dẫn
    When cùng học viên gửi lại yêu cầu tương đương
    Then hệ thống không tạo thêm đăng ký trùng
    And học viên nhận trạng thái nhất quán của đăng ký hiện có
~~~

Đây là ví dụ diễn đạt hành vi, **không bắt buộc** sử dụng Cucumber hay một framework cụ thể. Nhóm vẫn cần kiểm tra tích hợp, phân quyền, lỗi mạng, khả năng vận hành và những rủi ro áp dụng.

### 11.6. Kết quả thử nghiệm sản phẩm và cải tiến

Sau khi Increment đã đạt tiêu chuẩn chất lượng và được mở thử phù hợp, nhóm có thể quan sát:

| Tín hiệu giả định | Quan sát minh họa | Câu hỏi tiếp theo |
|---|---|---|
| Đăng ký thành công | Phần lớn học viên thực hiện được luồng cơ bản. | Người học gặp khó ở bước nào khi không hoàn thành? |
| Người dùng gửi lại yêu cầu | Một số người nhấn nút nhiều lần vì phản hồi giao diện chậm. | Có cần cải thiện thông báo đang xử lý không? |
| Lỗi vượt sức chứa | Không xuất hiện trong những trường hợp thử và giám sát đã xác định. | Bằng chứng có bao phủ đủ tình huống tải/cạnh tranh thực tế không? |
| Nhu cầu danh sách chờ | Nhiều người hỏi cách đăng ký khi buổi đã đầy. | Có nên thử danh sách chờ ở một Increment sau? |

Kết quả có thể khiến nhóm ưu tiên cải thiện phản hồi giao diện và kiểm chứng xử lý lặp trước khi đầu tư vào danh sách chờ phức tạp. XP giúp **đổi hướng kỹ thuật an toàn**, còn phản hồi sản phẩm giúp quyết định **đổi hướng có đáng làm hay không**.

## 12. Kết hợp XP với Scrum và Kanban

XP, Scrum và Kanban có trọng tâm khác nhau, nên có thể bổ sung nhau nếu nhóm sử dụng có chủ đích.

| Cách tiếp cận | Trọng tâm trong ví dụ đăng ký buổi học | Phản hồi/giá trị được hỗ trợ |
|---|---|---|
| **Scrum** | Product Goal, Sprint Goal, Product Backlog, Increment, Definition of Done và các sự kiện kiểm tra–thích ứng. | Nhóm có nhịp đánh giá mục tiêu và sản phẩm với stakeholder. |
| **Kanban** | Nhìn thấy trạng thái công việc, quản lý WIP, đo cycle time và giải quyết blocker. | Nhóm biết hạng mục đang chờ ở đâu và cải thiện dòng giao giá trị. |
| **XP** | TDD, pair programming, CI, refactoring, small releases, chia sẻ mã và phản hồi kỹ thuật. | Nhóm phát hiện sai lệch mã và tích hợp sớm, thay đổi an toàn hơn. |

### 12.1. Một nhóm Scrum có thể dùng kỹ thuật XP

Ví dụ, Scrum Team đặt Sprint Goal “Học viên đăng ký được một buổi hướng dẫn có giới hạn chỗ”. Developers dùng TDD cho quy tắc, pair programming cho logic ghi dữ liệu, CI để tích hợp và acceptance tests cho các trường hợp nghiệp vụ.

Scrum không quy định phải dùng TDD hoặc pair programming. Dù vậy, các thực hành XP có thể giúp Increment đáp ứng **Definition of Done** và giảm rủi ro trong Sprint.

Nếu khó khăn phát sinh, Developers và Product Owner có thể làm rõ, thương lượng phạm vi trong khi bảo vệ Sprint Goal và chất lượng; không nên bỏ kiểm thử để hoàn thành danh sách story bằng mọi giá.

### 12.2. Một nhóm Kanban có thể dùng kỹ thuật XP

Nhóm hỗ trợ sản phẩm theo luồng liên tục có thể dùng Kanban để quản lý yêu cầu và sự cố. Khi một hạng mục được kéo vào “Đang phát triển”, các kỹ thuật XP giúp nó đi qua kiểm tra và tích hợp nhanh hơn, giảm thời gian nằm ở “Chờ test” hoặc “Chờ merge”.

Nhóm có thể theo dõi work item age, blocked time, cycle time, throughput cùng sức khỏe CI. Khi pipeline đỏ kéo dài, đó là nút thắt có thể nhìn thấy và cần xử lý, không nên mở thêm nhiều việc mới để che việc dở dang.

### 12.3. Không nên ghép phương pháp thành tập hợp nghi thức nặng nề

Mục tiêu không phải áp tất cả cuộc họp của mọi phương pháp hoặc đòi mỗi hạng mục có thêm hàng chục tài liệu. Hãy chọn thực hành giúp giải quyết **nút thắt thực**:

- Sai quy tắc nghiệp vụ thường xuyên → làm rõ ví dụ và dùng TDD/acceptance tests.
- Lỗi chỉ phát hiện khi tích hợp → rút ngắn chu kỳ tích hợp và kiểm tra hợp đồng.
- Nhiều công việc đang mở → làm rõ WIP và ưu tiên hoàn thành.
- Thiết kế khó sửa → refactoring có kiểm chứng và chia sẻ tri thức.
- Giao tính năng nhưng ít người dùng → tạo Increment nhỏ hơn và lấy phản hồi sớm.

## 13. Phản hồi nhanh phải được đo và cải tiến như thế nào?

Một nhóm có thể cảm thấy làm việc nhanh hơn sau khi áp dụng XP, nhưng cần quan sát **cả tốc độ nhận tín hiệu, chất lượng và kết quả sản phẩm**.

| Tín hiệu | Cách hiểu thực dụng | Câu hỏi cải tiến |
|---|---|---|
| **Thời gian phản hồi kiểm tra cục bộ** | Mất bao lâu để biết thay đổi nhỏ có vượt qua kiểm tra cơ bản? | Có bài kiểm tra nào quá chậm hoặc khó chạy khiến mọi người bỏ qua không? |
| **CI feedback time** | Từ lúc tích hợp đến lúc có kết quả kiểm tra cần thiết. | Pipeline có cho kết quả đủ sớm và đủ tin để hành động không? |
| **Tỷ lệ build/pipeline không đạt** | Tần suất các lần kiểm tra phát hiện vấn đề. | Lỗi là sản phẩm thật hay test hỏng? Nhóm có xử lý kịp thời không? |
| **Flaky tests** | Kiểm thử có kết quả không ổn định khi điều kiện thực chất không đổi. | Có tín hiệu giả làm giảm niềm tin hoặc gây chạy lại vô ích không? |
| **Thời gian xử lý lỗi tích hợp** | Từ lúc phát hiện tới khi khôi phục trạng thái chung tin cậy. | Có phải tích hợp muộn hoặc thiếu người phối hợp không? |
| **Escaped defects** | Lỗi chỉ được phát hiện sau khi phần mềm đã bàn giao hoặc mở sử dụng. | Có loại rủi ro nào chưa được kiểm tra sớm? |
| **Cycle time và WIP** | Thời gian hoàn thành việc và lượng việc đang dở. | Phản hồi tốt hơn có giúp hạng mục tiến tới Done thay vì chờ lâu không? |
| **Change failure / khả năng khôi phục** | Tác động của thay đổi đến sự cố và thời gian phục hồi theo định nghĩa nhóm. | Nhóm có thể thay đổi thường xuyên mà vẫn đáng tin không? |
| **Outcome người dùng** | Hành vi hoặc kết quả thực tế sau khi nhận Increment. | Việc xây đúng kỹ thuật có tạo giá trị không? |

### 13.1. Ví dụ số liệu giả định

Giả sử nhóm thử rút ngắn vòng TDD/CI và tích hợp thường xuyên hơn trong ba giai đoạn:

| Chỉ số minh họa | Giai đoạn A | Giai đoạn B | Giai đoạn C |
|---|---:|---:|---:|
| Thời gian phản hồi CI trung vị (phút) | 28 | 16 | 8 |
| Hạng mục bị chặn vì tích hợp (hạng mục/giai đoạn) | 9 | 6 | 3 |
| Cycle time trung vị (ngày) | 12 | 9 | 7 |
| Lỗi nghiêm trọng phát hiện sau bàn giao | 5 | 3 | 2 |

**Dữ liệu này chỉ là ví dụ học cách phân tích, không phải bằng chứng về hiệu quả XP trong mọi tổ chức.** Xu hướng có vẻ tích cực, nhưng nhóm phải kiểm tra kích thước hạng mục, sự thay đổi về sản phẩm, tải công việc, năng lực và cách đo trước khi kết luận một thực hành đã gây ra kết quả.

### 13.2. Đừng tối ưu “CI xanh” bằng cách làm yếu kiểm thử

Nếu nhóm loại bỏ kiểm tra tích hợp quan trọng để pipeline từ 15 phút xuống 2 phút, chỉ số thời gian phản hồi đẹp lên nhưng rủi ro sản phẩm có thể tăng. Tương tự, nếu flaky test bị tắt mà không có biện pháp thay thế, pipeline xanh không còn phản ánh chất lượng thật.

Cần xem **thời gian phản hồi cùng độ tin cậy và phạm vi rủi ro được kiểm chứng**. Chất lượng của tín hiệu quan trọng hơn màu sắc của dashboard.

### 13.3. Phản hồi cũng cần được biến thành hành động

Một nhóm có nhiều thông báo kiểm thử nhưng không ai xử lý, hoặc có Retrospective chỉ ghi danh sách ý tưởng, vẫn thiếu khả năng học hỏi. Hãy xem:

- Ai nhìn thấy tín hiệu và có thể hành động?
- Có cách phân biệt lỗi nghiêm trọng với tiếng ồn không?
- Công việc sửa, ngăn tái diễn và kiểm tra lại có được theo dõi không?
- Khi kết quả người dùng trái dự đoán, backlog có được điều chỉnh không?

**Phản hồi nhanh chỉ có giá trị khi nhóm đủ năng lực và quyền hạn để thích ứng.**

## 14. Cách bắt đầu áp dụng XP mà không làm quá tải nhóm

Không cần tuyên bố áp dụng toàn bộ XP trong một ngày. Một đội mới có thể chọn một luồng công việc nhỏ, thiết lập tiêu chuẩn tối thiểu và mở rộng dựa trên bằng chứng.

### Giai đoạn 1 — Nhìn rõ khoảng trễ phản hồi hiện tại

Chọn một vài hạng mục gần đây và ghi:

- Lỗi yêu cầu thường được phát hiện khi nào?
- Lần đầu chạy unit test, integration test và acceptance test ở đâu trong luồng?
- Mã thường nằm tách nhánh bao lâu trước khi tích hợp?
- Pipeline thất bại có ai xử lý ngay không?
- Mọi người có tin kết quả kiểm tra không?
- Hạng mục Done có thực sự đáp ứng tiêu chuẩn chất lượng và tạo giá trị không?

Đừng vội áp đặt một công cụ nếu vấn đề chính là **thiếu người quyết định nghiệp vụ** hoặc **kiểm thử chưa có dữ liệu đại diện**.

### Giai đoạn 2 — Thử hai hoặc ba thực hành có tác động rõ

Ví dụ:

1. Chọn một quy tắc nghiệp vụ có thể kiểm thử và dùng **TDD vòng nhỏ**.
2. Thiết lập hoặc cải thiện **kiểm tra tự động khi tích hợp mã**.
3. Áp dụng **pair programming** cho thay đổi có rủi ro lớn hoặc vùng code ít người hiểu.

Giữ thay đổi ở quy mô mà nhóm có thể quan sát và điều chỉnh. Không đặt mục tiêu “100% số dòng mã được bao phủ bởi test” nếu chỉ số đó không phản ánh rủi ro thật.

### Giai đoạn 3 — Kết nối phản hồi kỹ thuật với phản hồi sản phẩm

Làm rõ user story và ví dụ cùng người hiểu nghiệp vụ. Chia thành lát nhỏ có thể đánh giá, không chỉ chia theo database–API–UI. Khi Increment đủ chất lượng, xem phản hồi thực tế để quyết định bước tiếp.

Nếu TDD giúp nhóm viết mã đúng nhanh hơn nhưng vẫn liên tục xây tính năng ít người cần, vấn đề có thể nằm ở **khám phá sản phẩm**, cần cải tiến song song.

### Giai đoạn 4 — Cải tiến thiết kế và khả năng cộng tác

Khi kiểm thử đáng tin hơn, dùng **refactoring** để loại bỏ cấu trúc làm thay đổi khó khăn. Tăng chia sẻ tri thức, quy ước mã và sở hữu chung; tránh để chỉ một người có thể sửa phần quan trọng.

### Giai đoạn 5 — Đánh giá và điều chỉnh

Sau một vài chu kỳ, so sánh dữ liệu và quan sát trực tiếp: lỗi phát hiện sớm hơn không, thời gian chờ tích hợp có giảm không, chất lượng có giữ được không, người dùng có nhận phản hồi sớm hơn không?

Nếu một thực hành gây nhiều chi phí mà ít giá trị trong bối cảnh cụ thể, hãy điều chỉnh cách áp dụng. **Kỷ luật XP không có nghĩa cứng nhắc; nó nhằm tạo điều kiện phản hồi và cải tiến liên tục.**

## 15. Những phản mẫu thường gặp khi nói về XP

| Phản mẫu | Vì sao nguy hiểm? | Cách cải thiện |
|---|---|---|
| “Extreme” nghĩa là tăng ca và viết mã thật nhiều. | Làm cạn năng lực, tăng lỗi và giảm phản hồi đáng tin. | Duy trì nhịp làm việc bền vững và kỹ thuật kiểm chứng. |
| Chạy unit test nhanh là đủ. | Bỏ sót lỗi tích hợp, cạnh tranh, bảo mật và nhu cầu người dùng. | Kết hợp các mức phản hồi theo rủi ro. |
| Viết test sau khi xong tất cả rồi gọi là TDD. | Không có vòng Red–Green–Refactor dẫn dắt từng bước. | Thực hành test-first ở những đơn vị hành vi phù hợp. |
| Kiểm thử bám từng chi tiết implementation. | Refactoring nhỏ làm nhiều test hỏng dù hành vi không đổi. | Ưu tiên kiểm tra hợp đồng và hành vi ổn định ở mức phù hợp. |
| TDD bắt buộc thay thế kiểm thử khám phá. | Những rủi ro chưa từng nghĩ tới không có test để phát hiện. | Giữ kiểm thử khám phá và đánh giá chất lượng theo rủi ro. |
| Pair programming là một người gõ, một người giám sát. | Giảm cộng tác và học hỏi, tạo quan hệ không bình đẳng. | Cùng giải quyết vấn đề, hỏi–đáp và đổi vai thường xuyên. |
| Pair mọi việc bất kể mục tiêu. | Tốn năng lực khi không tạo thêm phản hồi hữu ích. | Chọn kiểu cộng tác theo độ phức tạp, rủi ro và nhu cầu chia sẻ. |
| CI chỉ chạy cuối tuần. | Xung đột và sai hợp đồng tích tụ trước khi phát hiện. | Tích hợp thay đổi nhỏ thường xuyên và xử lý pipeline hỏng kịp thời. |
| Chạy lại flaky test cho tới khi xanh. | Tín hiệu mất đáng tin, lỗi thật dễ bị bỏ qua. | Điều tra và sửa tính không ổn định; ghi rõ giới hạn của test. |
| Refactoring chính là thêm tính năng. | Khó biết hành vi thay đổi do đâu, test hồi quy khó phân tích. | Tách bước đổi cấu trúc và bước đổi hành vi khi có thể. |
| Simple design nghĩa là bỏ qua độ tin cậy. | “Đơn giản” sai bối cảnh có thể gây mất tiền, dữ liệu hoặc quyền riêng tư. | Chọn mức phức tạp tối thiểu vẫn đáp ứng ràng buộc thật. |
| Collective ownership nghĩa là ai sửa cũng được, không cần kiểm tra. | Lỗi lan rộng và vi phạm quy trình bảo vệ. | Dùng kiểm thử, tiêu chuẩn mã và cơ chế rà soát phù hợp. |
| Nhiều test xanh nghĩa là người dùng đã hài lòng. | Lẫn chất lượng kỹ thuật với outcome. | Kết hợp phản hồi sản phẩm và quan sát sử dụng. |
| Phát hành nhỏ nghĩa là có thể bỏ DoD. | Lỗi nghiêm trọng lọt ra sớm hơn. | Chia nhỏ phạm vi, không chia nhỏ tiêu chuẩn an toàn thiết yếu. |
| Đo hiệu quả XP bằng số test hoặc tỷ lệ coverage duy nhất. | Dễ tối ưu số lượng test nhưng thiếu kiểm tra quan trọng. | Xem độ tin cậy tín hiệu, lỗi thoát, khả năng tích hợp, flow và outcome. |

## 16. Bài thực hành: thiết kế một vòng phản hồi ngắn

Một nhóm đang xây chức năng **hủy đăng ký buổi học** với các yêu cầu:

- Học viên chỉ được hủy đăng ký của chính mình.
- Nếu hủy trước thời điểm chốt danh sách, chỗ trống được trả lại.
- Gửi lại cùng một yêu cầu không được tăng số chỗ trống hai lần.
- Nếu cập nhật dữ liệu thất bại, không được thông báo “hủy thành công”.

### Bài tập 1 — Chọn kiểm thử Red đầu tiên

Hãy đề xuất một hành vi nhỏ có thể kiểm tra trước khi viết mã.

**Gợi ý:** viết unit test cho quy tắc học viên sở hữu đăng ký và trạng thái còn được phép hủy; sau đó viết lượng mã tối thiểu đáp ứng. Không cần khởi đầu bằng toàn bộ quy trình hủy trên giao diện.

### Bài tập 2 — Chỉ ra rủi ro unit test không phát hiện

Điều gì xảy ra nếu hai yêu cầu hủy gửi gần đồng thời hoặc hệ thống nhắc lại một sự kiện?

**Gợi ý:** cần kiểm chứng cách cập nhật trạng thái và chỗ trống **nguyên tử/nhất quán**, xử lý lặp an toàn và các tình huống lỗi tích hợp. Một hàm kiểm tra quyền đã qua unit test chưa đủ bảo vệ giao dịch thực tế.

### Bài tập 3 — Thiết kế pipeline phản hồi

Bạn sẽ chạy kiểm tra nào thường xuyên tại máy lập trình viên và kiểm tra nào khi tích hợp?

**Gợi ý:** dùng biên dịch, unit tests và kiểm tra tĩnh nhanh ở vòng cục bộ; bổ sung kiểm tra hợp đồng, tích hợp cơ sở dữ liệu và luồng hủy theo rủi ro ở CI. Các thử nghiệm sâu hơn có thể chạy theo lịch hoặc khi thay đổi thành phần liên quan, nhưng phải giữ các tiêu chuẩn chất lượng bắt buộc.

### Bài tập 4 — Xác định khi nào cần phản hồi người dùng

Nếu kỹ thuật hủy đăng ký đã đúng, làm sao biết học viên tìm được nút hủy và hiểu hậu quả?

**Gợi ý:** dùng tiêu chí chấp nhận về thông tin hiển thị, thử hành trình với người dùng phù hợp, quan sát sự hiểu nhầm và chỉnh backlog. Test xanh chỉ chứng minh những hành vi đã được kiểm chứng ở mức tương ứng.

### Bài tập 5 — Chọn một cải tiến nhỏ

Giả sử nhóm có nhiều test nhưng pipeline luôn mất quá lâu nên mọi người chỉ chạy khi gần phát hành.

**Gợi ý:** đo những bước chậm và lỗi thường phát hiện ở đâu; rút ngắn vòng kiểm tra cục bộ, chia bộ kiểm tra theo rủi ro, sửa flaky tests và tích hợp thường xuyên hơn. Sau đó xem độ trễ phát hiện lỗi, cycle time, chất lượng và độ tin cậy của tín hiệu có cải thiện không.

## 17. Checklist áp dụng XP và phản hồi kỹ thuật nhanh

Khi chuẩn bị làm một hạng mục:

- [ ] Đã rõ nhu cầu người dùng, quy tắc nghiệp vụ và ví dụ quan trọng chưa?
- [ ] Có thể chia công việc thành các thay đổi hoặc lát giá trị đủ nhỏ để kiểm tra sớm không?
- [ ] Những rủi ro cao về dữ liệu, bảo mật, xử lý lặp hoặc tích hợp đã được nhận diện chưa?
- [ ] Ai có thể trả lời câu hỏi nghiệp vụ khi xuất hiện bất định?

Trong lúc phát triển:

- [ ] Có bài kiểm tra nhanh cho quy tắc cốt lõi hoặc trường hợp biên phù hợp không?
- [ ] Nếu dùng TDD, kiểm thử Red có thất bại vì đúng lý do và vòng Green có nhỏ không?
- [ ] Refactoring có giữ hành vi đã được kiểm chứng không?
- [ ] Khi có vấn đề khó, nhóm có cơ chế pair hoặc trao đổi chuyên môn trực tiếp không?
- [ ] Thay đổi có được tích hợp đủ thường xuyên để tránh sai lệch giữa các nhánh không?
- [ ] Pipeline có đủ tin cậy; khi đỏ có ai chủ động xử lý không?
- [ ] Có kiểm tra hợp đồng, tích hợp, phân quyền và hành vi đồng thời khi rủi ro yêu cầu không?

Trước và sau khi bàn giao:

- [ ] Có tiêu chí chấp nhận và tiêu chuẩn chất lượng rõ; Increment có thực sự dùng được không?
- [ ] Có phân biệt tính năng đã kiểm tra bằng mock với khả năng đã tích hợp thật không?
- [ ] Những lỗi và giới hạn chưa kiểm chứng được minh bạch cho người quyết định phát hành không?
- [ ] Có cách lấy phản hồi về giá trị và trải nghiệm từ người dùng phù hợp không?
- [ ] Nhóm có theo dõi thời gian phản hồi, flaky tests, lỗi sau bàn giao và flow metrics không?
- [ ] Khi phát hiện vấn đề, có cải tiến cụ thể và kiểm tra lại tác động không?
- [ ] Nhịp làm việc có bền vững và các thành viên có thể chia sẻ tri thức không?

Checklist này là **công cụ tự kiểm tra**, không phải quy trình phê duyệt cứng. Nếu nhiều điều chưa đạt, nên chọn rủi ro đang gây chậm hoặc lỗi nhiều nhất, thử một cải tiến nhỏ và quan sát phản hồi.

## 18. Kết luận

**Extreme Programming** tạo khả năng thích ứng bằng việc kết hợp **kỷ luật kỹ thuật và cộng tác gần**. TDD cho phản hồi nhanh về hành vi ở mức mã; pair programming giúp phát hiện vấn đề thiết kế và chia sẻ tri thức khi làm việc; continuous integration phát hiện xung đột sớm; refactoring và simple design giữ cho phần mềm dễ thay đổi; các bản bàn giao nhỏ và trao đổi với người dùng giúp kiểm tra giá trị.

Các vòng phản hồi này **không thay thế nhau**. Unit test xanh chưa chứng minh tích hợp thật an toàn, pipeline xanh chưa chứng minh người dùng cần tính năng, và một bản demo đẹp chưa chứng minh dữ liệu được bảo vệ. Nhóm cần kết hợp các mức kiểm chứng theo rủi ro và giữ tiêu chuẩn chất lượng trước khi coi Increment dùng được.

Trong Agile Development, **phản hồi kỹ thuật nhanh là phương tiện để giảm thời gian phát hiện sai, hạn chế làm lại và hỗ trợ quyết định dựa trên bằng chứng**. Khi phối hợp XP với mục tiêu sản phẩm, backlog, Scrum hoặc Kanban một cách phù hợp, nhóm có thể **giao giá trị theo phần nhỏ, học sớm và đổi hướng an toàn mà vẫn duy trì chất lượng và nhịp phát triển bền vững**.

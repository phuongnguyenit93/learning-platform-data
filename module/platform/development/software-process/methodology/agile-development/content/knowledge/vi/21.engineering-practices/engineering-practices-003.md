# Thực hành kỹ thuật: Vòng lặp TDD và mối liên hệ với thiết kế mã

Một nhóm đang xây tính năng đăng ký workshop. Theo yêu cầu, nếu buổi học còn chỗ thì học viên có thể được xác nhận; nếu đã đầy chỗ, hệ thống phải từ chối thay vì ghi thêm đăng ký. Một lập trình viên triển khai ngay nhiều lớp xử lý, thêm vài điều kiện rồi viết test ở cuối. Khi Product Owner làm rõ trường hợp sức chứa bằng 0, số lượng dữ liệu bất hợp lệ và hai người đăng ký cùng lúc, nhóm phải sửa nhiều nơi. Lỗi xuất hiện ở tầng dữ liệu dù các phép kiểm tra đơn lẻ đều “xanh”.

**Test-Driven Development (TDD)** giúp nhóm tiếp cận thay đổi theo những vòng nhỏ: **viết một kiểm thử thất bại có ý nghĩa – viết lượng mã vừa đủ cho kiểm thử đạt – cải thiện thiết kế mà không đổi hành vi**. Sức mạnh của TDD không chỉ ở việc có nhiều test hơn. Việc buộc mô tả hành vi từ góc nhìn người sử dụng mã trước khi triển khai tạo phản hồi về **trách nhiệm của lớp, ranh giới phụ thuộc, API, độ gắn kết và khả năng thay đổi**.

TDD không thay thế việc hiểu yêu cầu, kiểm thử tích hợp, bảo mật hoặc kiểm chứng giá trị người dùng. Nó cũng không tự động tạo kiến trúc tốt nếu người viết test chỉ kiểm tra chi tiết triển khai. Bài này giúp hiểu **vòng lặp TDD và cơ chế nó tác động đến thiết kế mã**, kèm ví dụ Java/JUnit và một tình huống sản phẩm cụ thể.

Bài nằm trong mô-đun **AGILE_DEVELOPMENT**, nơi người học kết hợp nguyên tắc Agile với user story, backlog, Scrum, Kanban, XP và các chỉ số dòng công việc để giao phần mềm tăng dần, nhận phản hồi sớm và cải tiến liên tục. TDD là một thực hành kỹ thuật, đặc biệt gắn với Extreme Programming (XP), giúp các vòng phản hồi sản phẩm dựa trên phần mềm có chất lượng đủ tin cậy.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Giải thích **TDD** là gì và tại sao chu trình **Red – Green – Refactor** có ý nghĩa hơn việc “viết test sau khi đã code xong”.
2. Phân biệt **test thất bại đúng lý do**, test không chạy được do môi trường và test thất bại vì lỗi không liên quan.
3. Thực hiện một chuỗi TDD nhỏ bằng Java và JUnit 5 từ hành vi đầu tiên đến các trường hợp biên.
4. Giải thích vì sao bước Refactor có thể cải thiện **cohesion, coupling, tên gọi, ranh giới và tính dễ đọc** mà vẫn giữ hành vi quan sát được.
5. Dùng kết quả test để nhận diện thiết kế khó kiểm thử, phụ thuộc cứng, trạng thái ẩn và API mơ hồ.
6. Biết khi nào cần **test double**, tiêm phụ thuộc, đồng hồ giả lập, unit test, integration test hoặc acceptance test.
7. Nhận diện giới hạn của TDD đối với cạnh tranh dữ liệu, giao diện thực, bảo mật, hiệu năng và giá trị sản phẩm.
8. Kết hợp TDD với refinement, Definition of Done, continuous integration, pairing và vòng phản hồi Agile.
9. Phân tích các phản ví dụ như test quá bám implementation, test chậm/không ổn định và refactoring bị biến thành thêm tính năng.
10. Thiết kế một bài thực hành TDD có tiêu chí đánh giá cả hành vi lẫn thiết kế mã.

## 2. TDD là gì: một cách thiết kế có phản hồi nhanh

### 2.1. Định nghĩa thực hành

**Test-Driven Development** là cách phát triển trong đó một lập trình viên thường **chọn một hành vi rất nhỏ chưa được hệ thống đáp ứng**, viết kiểm thử tự động mô tả hành vi đó, quan sát kiểm thử thất bại theo lý do dự kiến, triển khai đủ để nó đạt, rồi cải thiện mã trong khi các kiểm thử vẫn đạt.

Chu trình cốt lõi:

~~~mermaid
flowchart LR
    A[Chọn một hành vi nhỏ] --> B[RED: viết test thất bại đúng lý do]
    B --> C[GREEN: viết mã tối thiểu để test đạt]
    C --> D[REFACTOR: cải thiện thiết kế, giữ hành vi]
    D --> E[Chạy các kiểm thử liên quan]
    E --> A
~~~

Đây là **vòng phản hồi rất ngắn ở mức kỹ thuật**, có thể diễn ra nhiều lần trong một phiên lập trình. Nó khác vòng phản hồi của Sprint Review hay dùng thử người dùng, nhưng chúng bổ trợ nhau.

TDD trả lời một câu hỏi rất cụ thể: **“Nếu mã này phải đáp ứng hành vi vừa nêu, bằng chứng tự động gần nhất là gì, và thiết kế nào giúp đáp ứng nó một cách đơn giản?”**

### 2.2. Vì sao test được viết trước?

Khi viết test trước, người phát triển tạm đứng ở vị trí **người sử dụng API** của đoạn mã sẽ tạo. Những câu hỏi thiết kế xuất hiện sớm:

- Nên gọi hành vi bằng tên nào?
- Đầu vào, đầu ra nào người gọi cần biết?
- Trường hợp lỗi được biểu diễn ra sao?
- Có phải tạo cả một hệ thống bên ngoài mới kiểm tra được quy tắc nhỏ này không?
- Lớp có đang nhận quá nhiều trách nhiệm?
- Điều kiện nào là bất biến của miền nghiệp vụ?
- Cần cung cấp phụ thuộc nào từ bên ngoài để hành vi có thể kiểm soát được?

Một lớp có API khó gọi trong test thường **cũng khó dùng, khó hiểu hoặc khó thay đổi** trong mã ứng dụng. Tuy nhiên, tính dễ test không phải tiêu chí duy nhất của thiết kế tốt: vẫn phải cân nhắc tính đúng, bảo mật, hiệu năng, vận hành và sự phù hợp với miền nghiệp vụ.

### 2.3. TDD khác “viết test sau”

| Cách tiếp cận | Trình tự điển hình | Điểm mạnh | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| **TDD** | Test đỏ → mã xanh → refactor, lặp nhỏ | Phản hồi trước triển khai; API và trách nhiệm có thể được cân nhắc sớm | Test sai trọng tâm vẫn có thể dẫn đến thiết kế kém |
| **Test sau triển khai** | Viết mã → viết test để xác nhận | Có thể phù hợp cho mã khám phá, ứng dụng hiện có | Dễ kiểm tra lại đúng những gì đã code thay vì hành vi cần có |
| **Chỉ kiểm thử thủ công** | Triển khai → thử qua giao diện/người dùng | Khám phá trải nghiệm và lỗi khó tự động | Khó lặp nhanh, dễ bỏ sót hồi quy |
| **Phát triển không có phản hồi kiểm thử** | Triển khai nhiều mã rồi mới kiểm tra cuối kỳ | Có thể cho cảm giác nhanh ban đầu | Rủi ro lỗi tích lũy và sửa lại muộn |

TDD không chứng minh rằng mọi tình huống “test trước” sẽ hiệu quả hơn “test sau”. Giá trị nằm ở **vòng kiểm tra ngắn, đúng và đủ tin cậy**, cùng cách dùng phản hồi để cải thiện thiết kế.

### 2.4. TDD ở mức nào?

Trong thực tế có nhiều phạm vi:
- **Unit-level TDD:** thúc đẩy quy tắc nhỏ, một lớp hoặc nhóm đối tượng hợp tác.
- **Outside-in TDD:** bắt đầu từ hành vi qua ranh giới hệ thống, dùng các test ở mức cao dẫn đường rồi xây các đơn vị bên trong.
- **Acceptance-test-driven development (ATDD):** nhóm làm rõ tiêu chí chấp nhận trước khi triển khai, thường có nghiệp vụ, kiểm thử và phát triển cùng tham gia.

Bài này tập trung vào **unit-level TDD và tác động đến thiết kế**, đồng thời giải thích cách kết nối với kiểm thử ở các cấp cao hơn.

## 3. Hiểu đúng ba bước Red – Green – Refactor

### 3.1. Red: test mới phải thất bại đúng lý do

**Red** là lúc viết một kiểm thử mô tả điều hệ thống **chưa làm được**, sau đó chạy để xác nhận tín hiệu thất bại có ý nghĩa.

Ví dụ muốn một quy tắc trả lời “còn chỗ để xác nhận không?”:
- Test cung cấp số người đã xác nhận và sức chứa.
- Kết quả mong đợi là **có thể xác nhận** khi số đã xác nhận nhỏ hơn sức chứa.
- Ở bước đầu, triển khai chưa có hành vi này nên test thất bại.

**Không nên coi mọi màu đỏ là thành công của Red.** Nếu test không biên dịch vì gõ sai tên lớp, không chạy vì thiếu cấu hình hoặc thất bại do mất kết nối dữ liệu không liên quan, nó chưa xác nhận được yêu cầu nghiệp vụ mà bạn định kiểm tra.

Một bước Red tốt:
1. Có tên test diễn đạt hành vi.
2. Có đầu vào đủ nhỏ và dễ hiểu.
3. Có kết quả kỳ vọng rõ.
4. Thất bại theo **lý do dự kiến**.
5. Không phụ thuộc vào thời gian, mạng hay thứ tự chạy một cách khó kiểm soát.

### 3.2. Green: viết vừa đủ để đáp ứng test

Trong **Green**, nhiệm vụ là **khiến kiểm thử mới và các kiểm thử liên quan đạt** bằng thay đổi đơn giản nhất hợp lý.

Đừng tự thêm những lớp, tùy chọn, chiến lược hoặc bảng dữ liệu chưa có nhu cầu. Nếu hiện chỉ cần so sánh sức chứa, một điều kiện đơn giản có thể là đủ.

**Green không có nghĩa viết mã bừa hoặc cố tình bỏ bảo mật.** Nó là lời nhắc không giải quyết trước mười vấn đề giả định trong khi chưa có bằng chứng; vẫn tôn trọng ràng buộc thiết yếu của nghiệp vụ và DoD.

### 3.3. Refactor: cải thiện cấu trúc, không đổi hành vi

Khi test xanh, hãy quan sát mã:
- Tên phương thức có nói đúng ý nghĩa không?
- Có biểu thức bị lặp?
- Quy tắc nghiệp vụ có nằm đúng lớp?
- Có quá nhiều điều kiện trong một hàm?
- Có phụ thuộc khiến test hoặc mã gọi trở nên khó không?
- Có bước nào giúp cấu trúc dễ đọc hơn **mà không thay đổi kết quả quan sát được**?

**Refactoring** là thay đổi cấu trúc trong khi giữ hành vi. Nếu trong bước “refactor” bạn thêm chính sách mới, thay API theo nghĩa nghiệp vụ hoặc sửa cách xử lý trường hợp lỗi, bạn đã **thay đổi hành vi**; việc đó cần test mới và một vòng Red–Green rõ ràng.

### 3.4. Vì sao không bỏ qua Refactor?

Nếu chỉ lặp Red–Green, mã có thể tích lũy:
- Các điều kiện trùng lặp.
- Tên biến mơ hồ.
- Các hàm lớn chứa nhiều trách nhiệm.
- Những phụ thuộc cứng để “chạy cho qua test”.
- Test chồng chéo cùng chi tiết triển khai.

**Refactor là phần nối TDD với thiết kế mã.** Việc có test hồi quy làm nhóm tự tin hơn để đơn giản hóa cấu trúc từng bước, nhưng test không đầy đủ không bảo đảm mọi thay đổi đều an toàn.

### 3.5. Một vòng nên nhỏ tới đâu?

Một vòng tốt đủ nhỏ để **khi test đỏ biết mình vừa thay đổi điều gì**, và khi refactor biết hành vi nào phải giữ. Có thể là:
- Một giá trị trả về mới.
- Một trường hợp biên.
- Một loại lỗi hợp lệ.
- Một quy tắc chuyển trạng thái.
- Một phụ thuộc cần được đưa qua interface.
- Một đoạn lặp được đặt tên rõ.

Không có quy định TDD rằng mỗi vòng phải kéo dài đúng một phút hoặc chỉ có một dòng mã. Vòng càng lớn, **tín hiệu lỗi càng khó khoanh vùng**; cần điều chỉnh theo mức phức tạp và khả năng học của nhóm.

## 4. Thực hành Java/JUnit: xây quy tắc chỗ trống bằng TDD

Ví dụ xuyên suốt là **SeatAvailabilityPolicy**, một đối tượng quyết định liệu có thể xác nhận thêm một người vào workshop hay không dựa trên **số đã xác nhận** và **sức chứa**. Trong bước đầu ta cố tình chỉ kiểm tra quy tắc thuần túy, chưa xử lý cơ sở dữ liệu hoặc cạnh tranh.

**Giả định minh họa:** số đã xác nhận và sức chứa đều là số nguyên không âm; số đã xác nhận không được vượt sức chứa. Đầu vào vi phạm những bất biến đó sẽ được coi là không hợp lệ.

### 4.1. Vòng 1 – Red: còn chỗ thì cho phép

Viết test JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class SeatAvailabilityPolicyTest {

    @Test
    void allowsConfirmationWhenOneSeatRemains() {
        SeatAvailabilityPolicy policy = new SeatAvailabilityPolicy();

        boolean allowed = policy.canConfirm(9, 10);

        assertTrue(allowed);
    }
}
~~~

Để bài test **biên dịch và thất bại đúng lý do**, tạo một lớp tối thiểu có API cần thiết nhưng chưa triển khai hành vi:

~~~java
public final class SeatAvailabilityPolicy {

    public boolean canConfirm(int confirmed, int capacity) {
        return false;
    }
}
~~~

Khi chạy test, kết quả mong đợi là **thất bại do actual = false nhưng expected = true**. Đây là một vòng Red có ý nghĩa: test chỉ ra chính xác hành vi còn thiếu, chứ không phải lỗi môi trường.

### 4.2. Vòng 1 – Green: triển khai vừa đủ

Thay phương thức bằng:

~~~java
public boolean canConfirm(int confirmed, int capacity) {
    return confirmed < capacity;
}
~~~

Test mới đạt với dữ liệu 9 và 10. Chưa cần tạo repository, event bus, lớp thông báo hoặc tầng HTTP vì **quy tắc đang kiểm tra chưa cần đến chúng**.

Nhưng giờ phải hỏi: test duy nhất có bảo vệ được những ranh giới quan trọng không? Chưa.

### 4.3. Vòng 2 – Ràng buộc đầu vào không hợp lệ

Nhóm xác định đầu vào âm là sai dữ liệu và cần được phát hiện rõ, thay vì trả một kết quả nghiệp vụ như thể dữ liệu bình thường.

Thêm test:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

@Test
void rejectsNegativeConfirmedCount() {
    SeatAvailabilityPolicy policy = new SeatAvailabilityPolicy();

    assertThrows(
        IllegalArgumentException.class,
        () -> policy.canConfirm(-1, 10)
    );
}
~~~

Ở thời điểm này, mã Green trước đó trả về **true** cho -1 nhỏ hơn 10, vì vậy test thất bại đúng lý do: chưa có kiểm tra dữ liệu đầu vào.

Triển khai thêm kiểm tra:

~~~java
public boolean canConfirm(int confirmed, int capacity) {
    if (confirmed < 0 || capacity < 0) {
        throw new IllegalArgumentException("Seat counts must be nonnegative");
    }
    return confirmed < capacity;
}
~~~

Chạy lại hai test. Cả hai phải đạt trước khi đổi thiết kế tiếp.

### 4.4. Vòng 3 – Bất biến không vượt sức chứa

Một trạng thái có **11 người đã xác nhận trong workshop sức chứa 10** là dữ liệu bất hợp lệ theo quy tắc minh họa. Bổ sung:

~~~java
@Test
void rejectsConfirmedCountGreaterThanCapacity() {
    SeatAvailabilityPolicy policy = new SeatAvailabilityPolicy();

    assertThrows(
        IllegalArgumentException.class,
        () -> policy.canConfirm(11, 10)
    );
}
~~~

Trước khi sửa, mã chỉ trả về false nên test đỏ. Bổ sung điều kiện **confirmed > capacity** để nó xanh.

Một test biên có ích khác là:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;

@Test
void refusesConfirmationWhenWorkshopIsFull() {
    SeatAvailabilityPolicy policy = new SeatAvailabilityPolicy();

    assertFalse(policy.canConfirm(10, 10));
}
~~~

Trường hợp này có thể **đã xanh** với triển khai hiện tại. Nó vẫn có giá trị làm tài liệu và kiểm thử hồi quy, nhưng **không phải một bước Red mới thúc đẩy tính năng chưa có**. Người thực hành không cần cố làm test đang đúng trở thành đỏ bằng cách phá mã; hãy chọn quy tắc chưa được hỗ trợ cho vòng kế tiếp.

### 4.5. Refactor: gọi tên bất biến rõ ràng

Sau khi các test xanh, nếu điều kiện dài hoặc được dùng lại ở những điểm thích hợp, có thể tách kiểm tra dữ liệu thành phương thức ngắn:

~~~java
public final class SeatAvailabilityPolicy {

    public boolean canConfirm(int confirmed, int capacity) {
        validateCounts(confirmed, capacity);
        return confirmed < capacity;
    }

    private void validateCounts(int confirmed, int capacity) {
        if (confirmed < 0 || capacity < 0 || confirmed > capacity) {
            throw new IllegalArgumentException("Invalid seat counts");
        }
    }
}
~~~

Ở bước này ta **chỉ đổi cấu trúc** so với trạng thái đã có các điều kiện tương đương, không thêm quy tắc nghiệp vụ. Chạy toàn bộ test liên quan phải vẫn xanh.

**Không phải cứ tách phương thức là thiết kế tốt hơn.** Nếu tên mới không thêm ý nghĩa hoặc tạo quá nhiều hàm chỉ gọi qua lại, giữ mã đơn giản ban đầu có thể tốt hơn.

### 4.6. Bảng bước đi của chuỗi TDD

| Vòng | Hành vi mới | Test ở Red | Mã ở Green | Điều quan sát về thiết kế |
| --- | --- | --- | --- | --- |
| 1 | Còn chỗ thì cho phép | 9/10 phải true | So sánh confirmed và capacity | Một đối tượng quy tắc thuần, API nhỏ |
| 2 | Dữ liệu âm là không hợp lệ | -1/10 phải ném lỗi | Kiểm tra giá trị âm | Quy tắc đầu vào cần rõ |
| 3 | Trạng thái vượt sức chứa là không hợp lệ | 11/10 phải ném lỗi | Kiểm tra bất biến | Domain invariant được thể hiện |
| Hồi quy | Hết chỗ thì từ chối | 10/10 phải false, có thể xanh sẵn | Không cần đổi | Test ghi rõ trường hợp biên |
| Refactor | Không đổi hành vi | Bộ test đang xanh | Đặt tên/tách validateCounts | Thiết kế được cải thiện có kiểm tra |

Những test trên **chưa chứng minh tính đúng trong môi trường đa luồng hoặc nhiều request**. Đó là vấn đề của ranh giới hệ thống khác được bàn ở phần sau.

## 5. TDD tác động đến thiết kế mã qua những cơ chế nào?

### 5.1. Thiết kế từ góc nhìn người gọi

Test viết trước khiến lập trình viên tự hỏi **một người dùng lớp này sẽ cần API nào**. Nếu câu chuyện chỉ là kiểm tra còn chỗ, API dạng:

~~~java
boolean canConfirm(int confirmed, int capacity)
~~~

dễ hiểu hơn một API yêu cầu trước tiên phải tạo controller, cấu hình HTTP, kết nối cơ sở dữ liệu và khởi tạo nhiều service chỉ để hỏi một điều kiện nghiệp vụ.

Không phải mọi hành vi đều có thể thu gọn thành hàm thuần. Nhưng bắt đầu từ nhu cầu sử dụng có thể chỉ ra **phần logic nào không cần biết cách lưu trữ hoặc truyền thông**.

### 5.2. Cohesion: một lý do thay đổi rõ hơn

**Cohesion (tính gắn kết)** nói về mức độ các trách nhiệm trong một thành phần cùng phục vụ một mục đích. Nếu một lớp vừa:
- Kiểm tra sức chứa.
- Ký hợp đồng SMS.
- Gửi email.
- Ghi log HTTP.
- Truy vấn database.
- Định dạng nội dung giao diện.

thì mỗi thay đổi nghiệp vụ hoặc tích hợp có thể làm lớp này phình to, kéo theo quá nhiều test và phụ thuộc.

Với TDD, một test nhỏ cho chính sách sức chứa giúp hỏi: “Có cần những trách nhiệm kia mới kiểm tra được điều này không?”. Nếu không, tách **quy tắc nghiệp vụ** khỏi **cơ chế kết nối và trình bày** có thể làm trách nhiệm rõ hơn.

### 5.3. Coupling: ranh giới phụ thuộc dễ thay đổi hơn

**Coupling (độ gắn kết giữa thành phần)** thể hiện mức phụ thuộc của một thành phần vào chi tiết của thành phần khác. Nếu test của chính sách chỗ bắt buộc kết nối máy chủ email hoặc cơ sở dữ liệu thật, rất có thể có phụ thuộc cần được xem lại.

Có thể tách:
- **Chính sách thuần** với dữ liệu đã nhận.
- **Dịch vụ điều phối** gọi repository và thực hiện nghiệp vụ.
- **Gateway** gửi thông báo.
- **Adapter** triển khai giao tiếp với database hoặc nhà cung cấp.

Mục tiêu không phải giảm mọi coupling xuống 0; thành phần **phải hợp tác** để tạo giá trị. Cần giảm sự phụ thuộc **không cần thiết vào chi tiết khó kiểm soát**, trong khi giữ các ranh giới có nghĩa với miền nghiệp vụ.

### 5.4. Tên gọi là một phần của thiết kế

Các test như:

~~~text
test1()
checkValue()
processAll()
~~~

không nói được hành vi hoặc quy tắc. Những cái tên như:

~~~text
allowsConfirmationWhenSeatRemains()
refusesConfirmationWhenFull()
rejectsNegativeConfirmedCount()
~~~

mang ý nghĩa của một bản đặc tả nhỏ.

Tên mã sản phẩm nên nhất quán với ngôn ngữ nghiệp vụ: **confirmed count**, **capacity**, **pending request**, **confirmed registration**. Đừng dùng tên trừu tượng khi miền nghiệp vụ đã có cách nói rõ hơn.

### 5.5. Bước Refactor như vòng thiết kế nổi lên từ phản hồi

Trong TDD, thiết kế có thể **hình thành dần** từ những yêu cầu đã được hiểu và những test cụ thể, thường được gọi là *emergent design*. Đây không phải cách nói rằng “không cần thiết kế trước”. Nhóm vẫn phải cân nhắc kiến trúc, chất lượng bảo mật, dữ liệu và phụ thuộc; nhưng tránh đóng cứng cấu trúc quá chi tiết cho nhu cầu chưa biết.

Một tiến trình:
1. Viết test cho một hành vi người dùng rõ.
2. Cài đặt cấu trúc đơn giản đủ dùng.
3. Nhìn sự trùng lặp hoặc phụ thuộc vừa xuất hiện.
4. Refactor khi có bằng chứng mã cần thiết kế lại.
5. Chạy test để bảo đảm vẫn giữ hành vi.
6. Lặp với trường hợp nghiệp vụ kế tiếp.

**TDD cho cơ hội phản hồi về thiết kế**, không phải bộ máy tự động sinh ra thiết kế tối ưu.

## 6. Tránh thiết kế quá sớm và tránh thiết kế quá muộn

### 6.1. Thiết kế quá sớm: abstractions cho tương lai chưa có

Nếu vừa cần kiểm tra còn chỗ, nhóm đã tạo:
- Hai mươi strategy cho từng kiểu workshop chưa tồn tại.
- Factory trừu tượng chỉ để tạo một policy.
- Hệ thống event bus cho hàm so sánh số nguyên.
- Một repository interface dù dữ liệu đầu vào đã được truyền vào.
- Hàng chục test mock để khẳng định từng lời gọi.

Những cấu trúc đó có thể tăng chi phí đọc và thay đổi mà không giảm rủi ro hiện tại. **Simple design** khuyến khích cấu trúc đơn giản **đủ đáp ứng nhu cầu thực đã biết**.

### 6.2. Thiết kế quá muộn: “chạy được là xong”

Chiều ngược lại là giữ mọi quy tắc trong một hàm lớn dù:
- Rất nhiều nhánh được lặp ở các điểm xử lý.
- Mỗi thay đổi gây lỗi ở nơi không liên quan.
- Không ai biết điều kiện nào là quy tắc nghiệp vụ.
- Test đòi khởi tạo nhiều hệ thống ngoài phạm vi cần kiểm tra.

Đó là dấu hiệu nên refactor có chủ đích. **Không cần viết lại tất cả**; chọn đoạn thay đổi thường xuyên hoặc có rủi ro, bổ sung test bảo vệ và cải thiện từng bước.

### 6.3. Triangulation: thêm ví dụ để tránh khái quát sai

Khi chỉ có test “9/10 được xác nhận”, một triển khai gian lận kiểu **return true** cũng làm test xanh. Một test thứ hai “10/10 bị từ chối” buộc mã xử lý được thêm tình huống. Test thứ ba “-1/10 bị từ chối hoặc báo dữ liệu lỗi theo hợp đồng” làm rõ bất biến.

Quá trình thêm những ví dụ có ý nghĩa giúp phân biệt **quy tắc tổng quát thực sự** với triển khai chỉ khớp một bộ dữ liệu.

Tuy nhiên, không nên tạo vô hạn test khác số đầu vào mà không thêm hiểu biết. Hãy ưu tiên **phân hoạch tương đương, giá trị biên, trạng thái và quy tắc**.

### 6.4. Không “code theo test” bất chấp mục đích

Một test có thể sai:
- Hiểu nhầm “gửi yêu cầu” là “đã xác nhận chỗ”.
- Giả định số âm là hợp lệ dù miền nghiệp vụ cấm.
- Đòi gửi email trong khi Product Owner chỉ yêu cầu hiển thị trạng thái.
- Bỏ qua quyền xem dữ liệu của người khác.

Khi phát hiện test sai, **sửa đặc tả và test** sau trao đổi nghiệp vụ. Không nên giữ một test thất bại về ý nghĩa chỉ vì “test đã viết trước” và ép mã sai theo nó.

## 7. TDD giúp lộ ra vấn đề testability và phụ thuộc

### 7.1. Một ví dụ khó test: gọi đồng hồ hệ thống trực tiếp

Giả sử cần xác định lúc nào gửi lời nhắc workshop. Nếu mã gọi đồng hồ thật ở nhiều vị trí, test phụ thuộc thời điểm thực và có thể chạy thất bại quanh giờ chuyển ngày.

Ví dụ logic minh họa:

~~~java
public final class ReminderPolicy {

    public boolean shouldRemindNow(java.time.Instant dueAt) {
        return !java.time.Instant.now().isBefore(dueAt);
    }
}
~~~

Test chạy ở bất kỳ thời điểm nào **không thể kiểm soát thời gian hiện tại** một cách trực tiếp. Nếu chỉ ngủ vài giây để chờ tới hạn, test vừa chậm vừa dễ không ổn định.

### 7.2. Thiết kế lại để nhận phụ thuộc từ bên ngoài

Đưa **Clock** vào constructor:

~~~java
import java.time.Clock;
import java.time.Instant;

public final class ReminderPolicy {
    private final Clock clock;

    public ReminderPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean shouldRemindNow(Instant dueAt) {
        return !Instant.now(clock).isBefore(dueAt);
    }
}
~~~

Test có thể dùng đồng hồ cố định:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class ReminderPolicyTest {

    private final Clock clock = Clock.fixed(
        Instant.parse("2026-04-10T09:00:00Z"),
        ZoneOffset.UTC
    );

    @Test
    void doesNotRemindBeforeDueTime() {
        ReminderPolicy policy = new ReminderPolicy(clock);

        boolean result = policy.shouldRemindNow(
            Instant.parse("2026-04-10T09:01:00Z")
        );

        assertFalse(result);
    }

    @Test
    void RemindsWhenDueTimeHasArrived() {
        ReminderPolicy policy = new ReminderPolicy(clock);

        boolean result = policy.shouldRemindNow(
            Instant.parse("2026-04-10T09:00:00Z")
        );

        assertTrue(result);
    }
}
~~~

Việc dùng **Clock.fixed** giúp test chạy lặp lại được. Lớp còn chỉ chịu trách nhiệm **ra quyết định khi nào**, không bị buộc phải tự gửi email hoặc truy cập mạng.

Nhưng tiêm phụ thuộc có chi phí: thêm tham số constructor, cấu hình và đôi khi cấu trúc. Với một hàm hoàn toàn thuần có thể nhận **now** trực tiếp, cách đó đôi khi còn đơn giản hơn. Chọn ranh giới phù hợp, không tiêm mọi thứ chỉ vì “testable”.

### 7.3. Dependency injection là phương tiện, không phải mục đích

Nếu một lớp tự tạo:
- Kết nối database.
- HTTP client.
- Bộ đọc file.
- Clock hệ thống.
- Gateway thông báo.

thì test có thể khó cô lập, chậm hoặc phụ thuộc môi trường.

**Dependency injection** cho phép cung cấp phụ thuộc từ ngoài. **Interface** có thể giúp tách hợp đồng hành vi khỏi chi tiết, nhưng không phải mọi lớp đều cần interface. Viết interface cho một hàm thuần không có phụ thuộc thay thế có thể chỉ làm kiến trúc phức tạp hơn.

### 7.4. Test doubles nên chọn theo mục tiêu test

| Test double / kỹ thuật | Cách dùng | Khi có ích | Rủi ro |
| --- | --- | --- | --- |
| **Stub** | Trả dữ liệu được chuẩn bị sẵn | Kiểm tra logic khi dependency cung cấp một trạng thái cụ thể | Phản hồi không giống thực tế |
| **Fake** | Triển khai đơn giản có hành vi, ví dụ kho dữ liệu trong bộ nhớ | Kiểm tra nhiều bước mà không cần dịch vụ thật | Có thể che lỗi transaction, dữ liệu hoặc đồng thời |
| **Spy** | Ghi nhận sự tương tác xảy ra | Khi lời gọi là kết quả có ý nghĩa, như gửi đúng một thông báo | Dễ tạo test phụ thuộc số lần gọi quá chi tiết |
| **Mock** | Thiết lập và kiểm tra kỳ vọng tương tác | Ranh giới ngoại vi có hợp đồng quan trọng | Test dễ vỡ khi refactor nội bộ |
| **Giá trị thật cố định** | Dùng đối tượng dữ liệu, Clock.fixed, collection đơn giản | Giữ test thực tế, nhanh, ít thiết lập | Không mô tả đủ tích hợp bên ngoài |

Đừng mock một phép cộng hoặc tất cả phương thức trong lớp chỉ để đạt “100% dependency injection”. Hãy ưu tiên **kiểm tra kết quả quan sát được** và dùng test double ở ranh giới thực sự cần kiểm soát.

## 8. Thiết kế tốt không chỉ là dễ unit test: giới hạn quan trọng của TDD

### 8.1. Quy tắc thuần khác giao dịch đồng thời

Trong ví dụ SeatAvailabilityPolicy, cả hai request có thể đọc **confirmed = 9, capacity = 10** gần đồng thời, đều nhận **true**, rồi cùng ghi xác nhận. Các unit test kiểm tra so sánh đúng nhưng **không bảo vệ được cập nhật dữ liệu nguyên tử**.

Một thiết kế hệ thống cần:
- Bất biến nghiệp vụ không vượt sức chứa.
- Cơ chế kiểm soát cạnh tranh tại lớp lưu trữ hoặc giao dịch phù hợp.
- Xử lý retry/idempotency và lỗi tạm thời khi cần.
- Kiểm thử tích hợp hoặc đồng thời sát cơ chế lưu trữ thực.
- Quan sát và xử lý trạng thái khi thao tác bị từ chối.

**Không có số lượng unit test thuần nào chứng minh được mọi đặc tính đồng thời của hệ thống thật.**

### 8.2. Trường hợp kiểm thử tích hợp minh họa

~~~gherkin
Tính năng: Không xác nhận vượt số chỗ workshop

  Tình huống: Hai học viên cạnh tranh suất cuối
    Cho trước một workshop có sức chứa 10
    Và đã có 9 đăng ký được xác nhận
    Khi hai yêu cầu xác nhận hợp lệ được xử lý gần đồng thời
    Thì tổng số đăng ký được xác nhận không vượt 10
    Và từng yêu cầu nhận kết quả nhất quán với dữ liệu đã lưu

  Tình huống: Gửi lại cùng yêu cầu do mạng lỗi
    Cho trước một yêu cầu đã được xử lý thành công
    Khi người dùng gửi lại cùng định danh yêu cầu
    Thì hệ thống không tạo hai xác nhận cho cùng yêu cầu
~~~

Các tình huống trên là **đặc tả minh họa**. Cách triển khai và kiểm thử phải phù hợp database, mô hình transaction và quy tắc nghiệp vụ thật; không thể chỉ tạo hai thread với timing tùy ý rồi kết luận đã kiểm tra mọi race condition.

### 8.3. Các tầng kiểm thử trả lời những câu hỏi khác nhau

| Tầng | Câu hỏi chính | Ví dụ workshop | Điều còn bỏ ngỏ |
| --- | --- | --- | --- |
| **Unit test** | Một quy tắc hay đối tượng phản hồi đúng theo đầu vào? | canConfirm(9,10) là true | Giao dịch thật có giữ bất biến không |
| **Component/service test** | Nhiều thành phần hợp tác qua một ranh giới? | RegistrationService gọi kho lưu trữ và nhận quyết định | Cấu hình production có đúng không |
| **Integration test** | Cơ sở dữ liệu, queue hoặc API phối hợp thật? | Hai đăng ký đồng thời không vượt sức chứa | Người dùng có hiểu kết quả không |
| **Acceptance/E2E test** | Luồng người dùng và chính sách nghiệp vụ đạt yêu cầu? | Học viên gửi, xem trạng thái và chỉ xem dữ liệu mình | Trải nghiệm thực trên nhiều bối cảnh |
| **Security/performance/resilience** | Ràng buộc phi chức năng và tình huống lỗi có được bảo vệ? | Quyền, tải, timeout, retry, phục hồi | Không thể đảm bảo tuyệt đối không còn lỗi |
| **User research/experiment** | Sản phẩm có tạo giá trị thật với người dùng? | Học viên ít phải hỏi lại trạng thái? | Suy luận nhân quả cần thiết kế phù hợp |

TDD tập trung vào vòng phản hồi phát triển. Một chiến lược chất lượng đáng tin cần **nhiều loại bằng chứng bổ sung**, không lấy một tỷ lệ coverage làm bảo đảm không có lỗi.

### 8.4. TDD không thay thế review và thiết kế kiến trúc

Một tập unit test xanh không chứng minh:
- API phù hợp hợp đồng liên nhóm.
- Truy cập dữ liệu được bảo vệ khi triển khai.
- Hệ thống đáp ứng hiệu năng mục tiêu.
- Có khả năng phục hồi sự cố.
- Người dùng hiểu trạng thái hay nhận giá trị.
- Kiến trúc không bị khóa bởi lựa chọn khó đảo ngược.

Vì vậy cần review có hiểu biết, đánh giá rủi ro, kiểm thử phù hợp và quan sát sản phẩm sau bàn giao.

## 9. Test tốt cần kiểm tra hành vi, không đóng băng mọi chi tiết triển khai

### 9.1. Test hành vi ổn định hơn test từng dòng mã

Một test mạnh quan tâm: “Khi workshop đầy, có từ chối xác nhận không?”. Một test dễ vỡ quan tâm: “Có gọi phương thức calculateAvailableSeats đúng ba lần, theo thứ tự này không?”, dù thứ tự gọi không phải hợp đồng của đối tượng.

Nếu refactoring đổi cấu trúc nội bộ mà giữ hành vi, **test hành vi vẫn xanh**. Test quá bám chi tiết có thể đỏ hàng loạt dù tính năng không đổi, làm chi phí đổi thiết kế tăng.

### 9.2. Khi nào nên kiểm tra tương tác?

Có những tương tác **chính là một phần của hợp đồng**:
- Không gửi hai thông báo cho cùng một sự kiện.
- Không gọi gateway thanh toán nếu xác nhận thất bại.
- Đảm bảo có yêu cầu ghi log kiểm toán ở ranh giới bắt buộc.
- Không lưu dữ liệu nếu quyền truy cập bị từ chối.

Khi đó spy/mock để xác nhận tương tác có thể phù hợp. Nhưng nên kiểm tra **ý nghĩa của tương tác**, không kiểm tra từng phương thức nội bộ chỉ vì test framework cho phép.

### 9.3. Thiết kế test theo Given – When – Then hoặc Arrange – Act – Assert

~~~text
Given / Arrange:
  Workshop còn một chỗ, dữ liệu hợp lệ.

When / Act:
  Học viên yêu cầu xác nhận.

Then / Assert:
  Quy tắc cho phép hoặc hệ thống lưu một xác nhận hợp lệ.
  Không vượt sức chứa, không lộ dữ liệu người khác.
~~~

Một test tốt đủ dữ liệu để người đọc hiểu **lý do thất bại** mà không phải theo dõi hàng chục biến chung.

### 9.4. Dấu hiệu test đang cản refactoring

- Đổi tên phương thức private khiến nhiều test đỏ dù API/hành vi không đổi.
- Test thiết lập quá nhiều mock cho một phép tính đơn giản.
- Test kiểm tra chi tiết logging phụ thay vì kết quả nghiệp vụ.
- Test ngủ tùy ý để chờ network/time.
- Một test chứa hàng chục hành vi, khi đỏ không biết phần nào hỏng.
- Test phải chạy theo thứ tự mới xanh.
- Người phát triển thường xuyên tắt test “vì biết nó flaky”.

Khi thấy các dấu hiệu này, nhóm nên **refactor cả test**: giảm setup, đặt tên rõ, kiểm soát dependency, chia trường hợp theo hành vi và dùng tầng kiểm thử phù hợp.

### 9.5. Coverage không phải thước đo thiết kế tốt

**Code coverage** cho biết bao nhiêu phần mã được chạy trong các test theo công cụ đo, **không cho biết các assertion đúng nghiệp vụ hay chưa**. Một test gọi phương thức rồi không kiểm tra kết quả vẫn có thể tăng coverage.

Không nên tối ưu 100% coverage bằng các test ít giá trị. Hãy ưu tiên **nguy cơ và hành vi quan trọng**, các trường hợp biên, lỗi, bảo mật và hồi quy đã từng xảy ra.

## 10. Refactoring từ tín hiệu của test: ví dụ ranh giới trách nhiệm

### 10.1. Bắt đầu từ một service ôm quá nhiều việc

Giả sử một lớp xử lý:
1. Kiểm tra còn chỗ.
2. Ghi xác nhận.
3. Gửi email.
4. Định dạng thông điệp.
5. Ghi log và phản hồi HTTP.

Một test cho chính sách sức chứa phải khởi tạo repository và email gateway. Đây có thể là **tín hiệu về coupling**: logic nghiệp vụ phụ thuộc các chi tiết không cần thiết.

### 10.2. Tìm ranh giới tách theo hành vi

Một cấu trúc có thể là:

~~~text
RegistrationController
        |
        v
RegistrationService  ----------> RegistrationRepository
        |
        +-----------------------> NotificationGateway
        |
        v
SeatAvailabilityPolicy
~~~

Ý nghĩa:
- **Policy** tính quyết định trên dữ liệu đã biết.
- **Service** điều phối quy tắc, transaction và kết quả.
- **Repository** chịu trách nhiệm đọc/ghi theo hợp đồng lưu trữ.
- **Gateway** phát thông báo theo kết quả đã xác nhận.
- **Controller** xử lý ranh giới HTTP và ánh xạ dữ liệu.

Đây chỉ là **một khả năng thiết kế**, không phải yêu cầu mọi dự án phải có đủ năm lớp. Đặc biệt, việc bảo vệ cạnh tranh dữ liệu phải được thiết kế ở transaction/khâu ghi thích hợp; không được coi policy thuần là cơ chế khóa duy nhất.

### 10.3. Test đơn vị dẫn thiết kế hợp đồng service

Một test có thể diễn đạt ý định:

> “Khi repository cho biết việc đặt suất cuối bị từ chối bởi cập nhật nguyên tử, service trả kết quả Full và không yêu cầu gửi thông báo xác nhận thành công.”

Ở mức này, repository có thể được thay bằng fake/stub để kiểm tra **cách service phản ứng với kết quả**; nhưng phải có **integration test với repository thật** để xác minh cơ chế cập nhật nguyên tử thực hiện đúng hợp đồng.

Đây là ví dụ TDD tạo động lực thiết kế **ranh giới rõ theo trách nhiệm**, không tạo một mạng lưới interface chỉ để mock mọi phương thức.

### 10.4. Không phải mọi thay đổi thiết kế đều xuất phát từ test

Quyết định cấu trúc dữ liệu, bảo mật, khả năng mở rộng hoặc giao tiếp liên hệ thống cần bằng chứng riêng. Test có thể mô tả ràng buộc quan sát được và bảo vệ refactoring, nhưng **không tự quyết định** một kiến trúc phân tán có cần thiết hay không.

Hãy kết hợp:
- Trường hợp sử dụng hiện tại.
- Ràng buộc an toàn và vận hành.
- Những thay đổi có khả năng xảy ra.
- Chi phí của abstractions.
- Khả năng đo và kiểm chứng.
- Phản hồi từ Developers, người vận hành và stakeholder.

## 11. TDD ngoài quy tắc thuần: outside-in và acceptance criteria

### 11.1. Bắt đầu từ user story có lợi ích rõ

User story minh họa:

> **Là học viên** đăng ký workshop, tôi muốn biết yêu cầu đã được tiếp nhận hay đã xác nhận chỗ, **để** không phải nhắn ban tổ chức hỏi lại sau khi gửi.

Câu chuyện này tạo ra câu hỏi **giá trị sản phẩm**. Acceptance criteria và thảo luận với Product Owner giúp làm rõ những trạng thái tồn tại và khi nào có thể hiển thị mỗi trạng thái.

### 11.2. Acceptance test làm rõ hành vi ở biên

~~~gherkin
Tính năng: Trạng thái đăng ký workshop

  Tình huống: Chưa xác nhận chỗ
    Cho trước học viên đã gửi yêu cầu hợp lệ
    Và điều phối viên chưa duyệt
    Khi học viên xem đăng ký của mình
    Thì trạng thái là "Đang chờ xác nhận"
    Và hệ thống không khẳng định đã giữ chỗ thành công

  Tình huống: Xác nhận thành công
    Cho trước yêu cầu đã được xác nhận hợp lệ
    Khi học viên xem đăng ký của mình
    Thì trạng thái là "Đã xác nhận"

  Tình huống: Không được truy cập đăng ký của người khác
    Cho trước người dùng không có quyền xem đăng ký X
    Khi người dùng truy cập đăng ký X
    Thì hệ thống không tiết lộ dữ liệu riêng của X
~~~

Các tình huống này **không thay thế TDD ở mức unit**; chúng giúp biết hệ thống cần làm gì từ góc nhìn người dùng. Sau đó Developers có thể dùng những vòng TDD nhỏ để xây quy tắc ánh xạ trạng thái, phân quyền và hành vi điều phối.

### 11.3. Outside-in khác inside-out thế nào?

| Cách tiếp cận | Điểm khởi đầu | Ưu điểm có thể có | Rủi ro |
| --- | --- | --- | --- |
| **Inside-out** | Một quy tắc lõi dễ hiểu, sau đó kết nối hệ thống | Khởi đầu nhỏ, nhanh và ít phụ thuộc | Tạo API lõi không khớp luồng người dùng nếu thiếu bối cảnh |
| **Outside-in** | Một hành vi qua ranh giới bên ngoài, sau đó thúc đẩy thiết kế bên trong | Giữ tập trung vào kết quả người gọi cần | Test mức cao có thể chậm, cần quản lý fake và hợp đồng |
| **Kết hợp có chủ đích** | Acceptance criteria xác định đích; unit TDD xây từng phần | Cân bằng nhu cầu sản phẩm và phản hồi kỹ thuật | Cần làm rõ cấp test nào đang chứng minh điều gì |

Không có một thứ tự áp dụng thích hợp cho mọi vấn đề. Quy tắc rõ, nhỏ có thể làm từ trong ra ngoài; luồng dịch vụ nhiều thành phần có thể cần acceptance test dẫn đường.

### 11.4. BDD, ATDD và TDD có liên quan nhưng không đồng nhất

- **TDD** là chu trình phát triển dựa trên kiểm thử thất bại, mã xanh và refactor.
- **BDD (Behavior-Driven Development)** nhấn mạnh mô tả hành vi dễ hiểu chung với nghiệp vụ, dùng ví dụ để làm rõ kỳ vọng.
- **ATDD** chú trọng sự cộng tác để xác định tiêu chí chấp nhận và kiểm tra từ trước khi thực hiện.
- **Gherkin** là một cách viết tình huống; **không phải cứ có Gherkin là tự động thực hành BDD hiệu quả**.
- **Unit test** là một loại kiểm thử; **không phải cứ có unit test là đã làm TDD**.

Kết nối đúng: nhóm hiểu mục tiêu người dùng, cùng thống nhất ví dụ nghiệp vụ, rồi dùng TDD để triển khai những thay đổi nhỏ có phản hồi nhanh.

## 12. TDD trong mã nguồn cũ: bắt đầu bằng hành vi đang có

### 12.1. Khi không có test, sửa code có thể rất rủi ro

Một lớp cũ có nhiều trường hợp đặc biệt, ít tài liệu và nhiều logic ẩn. Nếu viết lại trực tiếp để “code sạch” mà không biết hành vi hiện tại, nhóm có thể phá một ngoại lệ nghiệp vụ quan trọng.

Thực hành an toàn thường là:
1. Chọn phần cần thay đổi thật.
2. Quan sát hành vi hiện tại bằng dữ liệu và ví dụ có thể kiểm tra.
3. Tạo **characterization test** ghi nhận hành vi đang tồn tại.
4. Xác định phần nào là hành vi đúng cần giữ, phần nào là lỗi cần thay đổi.
5. Chọn một vòng Red–Green cho hành vi mới.
6. Refactor từng bước dưới bảo vệ của test.

### 12.2. Characterization test không đồng nghĩa hợp thức hóa mọi lỗi

Một characterization test có thể bảo vệ **hành vi hiện tại** để biết refactoring có làm thay đổi điều gì không. Nếu phát hiện hành vi sai nghiệp vụ, cần:
- Làm rõ hành vi mong muốn với người có trách nhiệm.
- Viết test mô tả kết quả đúng.
- Chấp nhận test đỏ tương ứng.
- Sửa mã theo một vòng TDD.
- Cập nhật hoặc bỏ test mô tả hành vi lỗi cũ.

Không giữ mã lỗi chỉ vì test cũ đang xanh.

### 12.3. Tạo điểm nối kiểm thử (*seam*) mà không viết lại toàn bộ

Nếu class cũ trực tiếp tạo HTTP client, có thể:
- Tách thao tác gọi dịch vụ ra một ranh giới rõ.
- Giữ nguyên hành vi trong bước refactor đầu tiên.
- Bổ sung test bảo vệ những quy tắc quan trọng.
- Sau đó đưa dependency vào để test nhanh và có kiểm soát.
- Bảo vệ thêm bằng integration test với dịch vụ thật hoặc môi trường phù hợp.

Mỗi bước cần có phạm vi và tín hiệu kiểm tra. Không cần “làm TDD đúng chuẩn” bằng cách xóa sạch code cũ rồi viết lại từ đầu.

### 12.4. Khi nào nên dùng spike?

Một **spike** là hoạt động khám phá có mục tiêu và giới hạn thời gian nhằm giảm bất định kỹ thuật. Ví dụ nhóm chưa biết cơ sở dữ liệu có thể bảo vệ cập nhật đồng thời bằng cơ chế nào. Họ có thể thử một mẫu nhỏ để trả lời câu hỏi trước khi thiết kế dịch vụ.

Spike không thay thế tiêu chuẩn hoàn tất của sản phẩm. Khi đưa code khám phá thành code sản phẩm, cần củng cố thiết kế, test và chất lượng phù hợp; không mặc định nguyên mẫu là giải pháp production.

## 13. TDD, CI và nhịp thay đổi bền vững

### 13.1. TDD cần phản hồi tin cậy và đủ nhanh

Nếu một vòng Red–Green mất 20 phút vì phải khởi tạo toàn bộ hệ thống, Developers khó duy trì nhịp thử một quy tắc nhỏ. Nếu test đôi khi xanh, đôi khi đỏ do timing không ổn định, tín hiệu mất giá trị.

Một bộ unit test giúp TDD nên:
- Chạy **nhanh đủ để chạy thường xuyên**.
- Có kết quả **lặp lại được**.
- Độc lập với thứ tự chạy.
- Thiết lập dữ liệu rõ và không làm bẩn môi trường chung.
- Tập trung vào hành vi quan trọng.
- Khi thất bại, giúp khoanh vùng nguyên nhân.

Không phải mọi kiểm thử hệ thống đều phải chạy vài mili-giây. Hãy phân loại vòng feedback: unit nhanh thường xuyên; integration và E2E ở các mốc phù hợp, nhất là trước khi phát hành.

### 13.2. Continuous integration mở rộng phản hồi

**Continuous integration (CI)** khuyến khích tích hợp thay đổi thường xuyên và chạy kiểm tra tự động, giúp phát hiện xung đột giữa các thay đổi sớm.

Ví dụ trình tự:
1. Thực hiện vài vòng Red–Green–Refactor trên máy.
2. Chạy unit test liên quan, rồi bộ kiểm tra phù hợp.
3. Tích hợp thay đổi nhỏ vào nhánh chung theo chính sách nhóm.
4. Pipeline chạy build, unit, integration/quality checks tương ứng.
5. Nếu pipeline đỏ, ưu tiên điều tra và khôi phục khả năng tin cậy.
6. Sau khi đáp ứng DoD và điều kiện vận hành, tạo Increment có thể bàn giao.

Không nên xem “CI xanh” như bằng chứng duy nhất của chất lượng: pipeline chỉ kiểm tra những gì được thiết kế và cấu hình để kiểm tra.

### 13.3. Refactor cùng test, không đợi đến “Sprint dọn code”

Khi có test bảo vệ, Developers có thể chỉnh tên, tách phương thức, giảm lặp và cải thiện cấu trúc ngay khi đang làm story. Những cải tiến lớn hơn vẫn cần cân nhắc rủi ro và ưu tiên, nhưng không nhất thiết gom mọi refactoring vào một giai đoạn đặc biệt cuối dự án.

**Giữ mã dễ thay đổi là công việc liên tục.** Nếu cứ trì hoãn mọi cải tiến thiết kế, mỗi story sau có thể đắt hơn story trước dù chức năng tương tự.

### 13.4. TDD và khả năng làm việc bền vững

TDD có thể **tăng chi phí ban đầu** ở một vùng mã chưa quen, nhưng kỳ vọng mang lại:
- Phát hiện lỗi gần lúc viết code.
- Giảm công việc sửa lại ở cuối vòng.
- Hỗ trợ đổi thiết kế an toàn hơn.
- Tạo tài liệu sống về hành vi.
- Giúp người mới hiểu quy tắc có thể kiểm tra.

Những lợi ích này cần **quan sát trong bối cảnh thực**. Đừng hứa TDD tự động tăng velocity hoặc loại bỏ hoàn toàn lỗi production.

## 14. TDD trong Scrum, Kanban và XP: vị trí đúng của một thực hành

### 14.1. Scrum: kỹ thuật hỗ trợ Definition of Done

Scrum không bắt buộc sử dụng TDD. Scrum xác định accountability, events, artifacts và commitments; Developers chịu trách nhiệm tạo **Increment đáp ứng Definition of Done**.

TDD có thể giúp Scrum Team:
- Làm rõ một trường hợp của Product Backlog item trong refinement.
- Tạo lát cắt nhỏ phù hợp Sprint Goal.
- Giữ kiểm tra liên tục trong Sprint, tránh dồn về cuối.
- Thực hiện refactoring với test bảo vệ.
- Trình bày ở Sprint Review một Increment đã đạt tiêu chuẩn, không chỉ một demo chưa tích hợp.
- Dùng Retrospective để kiểm tra xem thực hành kỹ thuật có giảm lỗi hoặc thời gian chờ không.

**Không dùng số test viết được để thay cho Sprint Goal.** Test và code là phương tiện; sản phẩm phải mang lại kết quả đáng giá cho người dùng.

### 14.2. Kanban: nhìn thấy tác động lên dòng việc

Kanban giúp nhóm định nghĩa luồng công việc, kiểm soát WIP và quan sát **cycle time, work item age, throughput**. TDD có thể ảnh hưởng tới những số liệu này theo hai hướng:
- **Giai đoạn đầu:** work item có thể cần thêm thời gian để tạo test và thiết kế an toàn.
- **Qua nhiều vòng:** ít lỗi làm lại hơn, review/tích hợp ổn định hơn và dự báo tốt hơn nếu thực hành phù hợp.

Để đánh giá, cần giữ **Definition of Workflow** và tập item tương đối nhất quán. Không nên đổi mốc Finished từ “merge” thành “đạt DoD” rồi kết luận cycle time tăng do TDD.

### 14.3. XP: một phần của bộ thực hành bổ trợ

Trong XP, TDD thường đi cùng:
- **Pair programming:** hai người cùng diễn đạt test, kiểm tra giả định và chia sẻ hiểu biết.
- **Simple design:** triển khai đủ giải quyết vấn đề hiện tại.
- **Refactoring:** cải thiện cấu trúc thường xuyên dưới bảo vệ của test.
- **Continuous integration:** phát hiện lỗi khi các thay đổi kết hợp.
- **Collective ownership:** mọi người có thể cải thiện vùng mã phù hợp với chuẩn chung.
- **Small releases:** giao phần mềm theo lát cắt nhỏ, nhận phản hồi nhanh.
- **Sustainable pace:** tránh phụ thuộc vào cứu lỗi và làm đêm kéo dài.

Chỉ áp dụng TDD nhưng bỏ CI, review, test tích hợp hoặc làm rõ user story có thể khiến lợi ích bị hạn chế. Cần nhìn **tính bổ trợ của các thực hành**, không chỉ tên của chúng.

## 15. Tình huống đầy đủ: từ backlog đến thiết kế mã có phản hồi

### 15.1. Bối cảnh

Một Scrum Team phát triển ứng dụng workshop. Product Goal là học viên tự đăng ký và nhận kết quả rõ, trong khi điều phối viên không xác nhận vượt số chỗ.

Product Backlog có các mục:
- WS-11: gửi yêu cầu đăng ký.
- WS-12: hiển thị trạng thái “đang chờ” và “đã xác nhận”.
- WS-13: chống xác nhận vượt sức chứa.
- WS-14: gửi thông báo kết quả qua kênh đã được xác minh giá trị.

Team chọn lát cắt WS-13 vì lỗi xác nhận trùng ảnh hưởng trực tiếp đến niềm tin và dữ liệu người dùng. Phần thông báo có thể được làm sau khi quy tắc xác nhận ổn định.

### 15.2. Làm rõ hành vi trước khi code

Product Owner và Developers xác nhận:
1. **Một suất còn lại** chỉ được xác nhận cho tối đa một yêu cầu.
2. Yêu cầu không hợp lệ không được ghi thành xác nhận.
3. Khi không còn suất, người dùng nhận trạng thái đúng; không nói “đã có chỗ”.
4. Dữ liệu đăng ký chỉ được xem bởi người có quyền.
5. Khi mất kết nối hoặc retry, hệ thống không sinh hai xác nhận cho cùng một yêu cầu hợp lệ.

Nhóm phân biệt **quy tắc thuần** với **điều kiện hệ thống**:
- Unit TDD cho so sánh sức chứa và đầu vào.
- Integration tests cho giao dịch đồng thời và lưu trữ.
- Acceptance tests cho kết quả và thông điệp người dùng.
- Security checks cho ranh giới quyền truy cập.

### 15.3. Một lát cắt TDD cụ thể

~~~text
Bước 1: RED
Test "khi đã xác nhận 9/10 chỗ thì còn một chỗ".
Test thất bại đúng lý do.

Bước 2: GREEN
Viết điều kiện so sánh tối thiểu.
Bộ test liên quan đạt.

Bước 3: RED
Test đầu vào số lượng âm phải bị từ chối.
Test thất bại vì mã chưa xác minh bất biến.

Bước 4: GREEN
Thêm kiểm tra đầu vào, không mở rộng chức năng ngoài nhu cầu.

Bước 5: REFACTOR
Đặt tên validateCounts, bỏ biểu thức lặp, giữ API rõ.
Chạy lại toàn bộ test liên quan.

Bước 6: TÍCH HỢP
Thiết kế giao dịch không xác nhận vượt chỗ.
Kiểm tra hai yêu cầu đồng thời trên kho lưu trữ thật.

Bước 7: CHẤT LƯỢNG SẢN PHẨM
Kiểm tra trạng thái hiển thị, quyền truy cập và retry.
Đối chiếu Definition of Done trước khi coi Increment hoàn tất.
~~~

**Điểm quan trọng:** TDD không yêu cầu chỉ kiểm tra bằng unit test. Lát cắt hữu ích cần **tập hợp bằng chứng về các ranh giới rủi ro khác nhau**.

### 15.4. Thiết kế được điều chỉnh thế nào?

Trước khi làm TDD, Developers định gom mọi thứ vào RegistrationController. Trong khi viết test họ nhận thấy kiểm tra sức chứa khó chạy nếu phải dựng HTTP, dữ liệu và email.

Nhóm lựa chọn:
- Tách chính sách sức chứa thành **domain policy** thuần.
- Để dịch vụ ứng dụng điều phối thao tác theo hợp đồng.
- Giao việc bảo vệ cạnh tranh cho **cơ chế dữ liệu/transaction** phù hợp và kiểm chứng bằng integration test.
- Tách phần thông báo khỏi quyết định sức chứa, chỉ gửi khi trạng thái đã được xác nhận nhất quán.
- Giữ Controller làm ranh giới trình bày, không chứa mọi điều kiện nghiệp vụ.

Quyết định này xuất phát từ **testability, trách nhiệm miền nghiệp vụ và rủi ro hệ thống**, không chỉ từ mong muốn “có nhiều lớp”.

### 15.5. Kiểm chứng tác động của thực hành

Sau vài vòng, nhóm có thể quan sát:
- Số lỗi xác nhận chỗ trong môi trường thử và production.
- Cycle time của user story cùng loại.
- Số lần phải quay lại sửa sau review hoặc phát hành.
- Thời gian pipeline phản hồi và mức độ ổn định.
- Tỷ lệ học viên hiểu đúng kết quả đăng ký.
- Những phần code phụ thuộc vào một người duy nhất.

**Dữ liệu có ích phải có bối cảnh:** nếu nhóm vừa nâng DoD hoặc tăng độ khó story, cycle time có thể thay đổi dù cách làm đang tốt hơn. Không được quy trực tiếp toàn bộ biến động cho TDD.

### 15.6. Ví dụ thảo luận Retrospective

> “Trong Sprint này, các test đơn vị giúp nhận diện quy tắc sức chứa rõ hơn, nhưng lỗi đồng thời chỉ được phát hiện ở integration test. Sprint tới, chúng ta sẽ làm rõ sớm những hạng mục có bất biến dữ liệu và đưa test tích hợp trường hợp cạnh tranh vào quy trình. Chúng ta sẽ xem các lỗi tương tự có được phát hiện trước review/phát hành hay không.”

Đó là một hành động cải tiến có thể kiểm chứng, khác với tuyên bố “TDD đã giải quyết mọi vấn đề”.

## 16. Những sai lầm thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Viết toàn bộ mã rồi mới thêm test và gọi là TDD | Mất vòng phản hồi thiết kế trước triển khai | Tập viết một test đỏ đúng lý do trước mỗi hành vi mới |
| Red vì lỗi setup hoặc cấu hình không liên quan | Không biết hành vi nào thiếu | Tạo test biên dịch/chạy được, kiểm tra failure đúng kỳ vọng |
| Viết quá nhiều test trước khi có Green | Phản hồi chậm, khó xác định bước sai | Chọn một trường hợp nhỏ, làm xanh rồi tiếp tục |
| Green bằng kiến trúc phức tạp ngoài nhu cầu | Tốn công, tăng gắn kết và khó đọc | Triển khai đơn giản đủ đáp ứng test và chất lượng |
| Bỏ Refactor trong mọi vòng | Mã tích lũy lặp, tên xấu và trách nhiệm mơ hồ | Kiểm tra cơ hội cải thiện khi test xanh |
| Dùng Refactor để thêm hành vi mới âm thầm | Khó biết thay đổi nào gây lỗi | Tách bước đổi hành vi sang một vòng Red–Green |
| Unit test bám thứ tự gọi hàm private | Test vỡ khi đổi thiết kế, dù hành vi không đổi | Ưu tiên kiểm tra hợp đồng và kết quả quan sát được |
| Mock mọi dependency kể cả phép tính đơn giản | Test phức tạp, bảo trì khó | Chỉ dùng test double ở ranh giới cần kiểm soát |
| Chỉ dùng unit test cho vấn đề đồng thời | Bỏ qua lỗi transaction/race condition | Thêm integration/concurrency tests trên hệ thống phù hợp |
| Tưởng coverage 100% nghĩa không còn lỗi | Bỏ qua giá trị assertion, bảo mật và khả năng sử dụng | Chọn test theo rủi ro, thêm các cấp kiểm tra cần thiết |
| Dùng thời gian thật và sleep trong unit test | Test chậm, flaky hoặc phụ thuộc múi giờ | Dùng Clock.fixed hay giá trị thời gian điều khiển được |
| Test phụ thuộc vào thứ tự chạy và dữ liệu chung | Kết quả không tái lập được | Cô lập fixture, làm sạch trạng thái và xác minh tính độc lập |
| Không kiểm tra màu đỏ sau khi đổi test | Test có thể không thực sự kiểm tra hành vi mới | Chạy và xem lỗi trước khi triển khai |
| Chỉ nhìn số test để đánh giá người lập trình | Khuyến khích test hình thức, bỏ chất lượng | Đánh giá kết quả nhóm và hành vi có giá trị |
| Viết abstraction sớm vì “TDD phải có interface” | Kiến trúc phức tạp không cần thiết | Chỉ tách khi có ranh giới trách nhiệm hoặc nhu cầu thay đổi thật |
| Bỏ qua acceptance criteria và Product Goal | Test xanh cho hành vi sai nhu cầu | Thảo luận ví dụ nghiệp vụ và kiểm tra outcome sau giao |
| Tắt test flaky để CI xanh | Tạo niềm tin giả và lỗi hồi quy bị bỏ sót | Điều tra nguyên nhân, tách test không ổn định có kiểm soát |
| Bắt đầu với legacy code bằng cách viết lại toàn bộ | Phá hành vi chưa hiểu | Thêm characterization tests và cải thiện từng bước |
| Coi TDD tự động cải thiện năng suất | Kỳ vọng không thực tế, gây áp lực bỏ test | Đo flow, quality và outcome với bối cảnh phù hợp |

## 17. Bài thực hành: một chuỗi TDD có thể giải thích

### 17.1. Bối cảnh

Nhóm phát triển dịch vụ đăng ký workshop. Có một chính sách cơ bản:

- Nếu số chỗ đã xác nhận nhỏ hơn sức chứa thì có thể xem xét xác nhận thêm.
- Nếu đã đủ thì từ chối.
- Số lượng âm hoặc số đã xác nhận lớn hơn sức chứa là dữ liệu không hợp lệ.
- Một request thực tế phải được kiểm soát cạnh tranh để không xác nhận vượt số chỗ.

Bạn sẽ triển khai **SeatAvailabilityPolicy** bằng Java/JUnit 5 và phân tích cách test ảnh hưởng thiết kế. Không cần xây đầy đủ API hoặc hệ thống gửi email trong bài đầu.

### 17.2. Nhiệm vụ A – Viết vòng Red đầu tiên (10 phút)

1. Viết test tên **allowsConfirmationWhenOneSeatRemains** với dữ liệu 9/10.
2. Tạo lớp và phương thức có chữ ký đơn giản để test biên dịch.
3. Để test thất bại với **false thay vì true**.
4. Giải thích vì sao đó là lỗi mong đợi của hành vi, không phải lỗi cấu hình JUnit.
5. Viết mã tối thiểu và chạy lại.

**Đáp án định hướng:** chữ ký có thể là boolean canConfirm(int confirmed, int capacity), test cần assertTrue với 9 và 10. Một stub return false tạo Red có ý nghĩa; Green là trả confirmed < capacity trong ví dụ ban đầu.

### 17.3. Nhiệm vụ B – Trường hợp biên và bất biến (15 phút)

Thêm các tình huống:

| Đầu vào | Hành vi mong muốn |
| --- | --- |
| confirmed = 9, capacity = 10 | true |
| confirmed = 10, capacity = 10 | false |
| confirmed = 0, capacity = 0 | false |
| confirmed = -1, capacity = 10 | IllegalArgumentException |
| confirmed = 1, capacity = -1 | IllegalArgumentException |
| confirmed = 11, capacity = 10 | IllegalArgumentException |

Yêu cầu:
1. Chọn tình huống nào **đang thất bại** để thúc đẩy vòng Red kế tiếp.
2. Viết test và chạy trước khi sửa.
3. Làm xanh bằng thay đổi tối thiểu.
4. Kiểm tra các test có chồng chéo vô ích hay không.
5. Viết rõ vì sao số đã xác nhận lớn hơn sức chứa được xem là bất biến dữ liệu.

**Gợi ý:** một test mới đã xanh vì mã tình cờ xử lý đúng vẫn có thể giữ làm hồi quy. Không phá mã chỉ để làm test đỏ; hãy tìm hành vi còn thiếu. Các bất biến phải được thống nhất với nghiệp vụ thay vì áp đặt ngầm.

### 17.4. Nhiệm vụ C – Refactor nhưng giữ hành vi (15 phút)

Giả sử hàm chứa nhiều điều kiện. Hãy:
- Đặt lại tên biến rõ nghĩa.
- Xem có cần phương thức private **validateCounts** hay không.
- Xóa trùng lặp có ích.
- **Không đổi** chữ ký công khai nếu chưa có nhu cầu.
- Chạy lại toàn bộ test sau mỗi thay đổi nhỏ.
- Ghi một câu giải thích **tại sao cấu trúc mới dễ hiểu hơn**.

**Tiêu chí:** không chỉ “test xanh”, mà còn biết chỉ ra điều vừa thay đổi là **thiết kế**, không phải nghiệp vụ.

### 17.5. Nhiệm vụ D – Xử lý thời gian dễ test (15 phút)

Một lớp ReminderPolicy cần trả lời “đã đến lúc nhắc chưa?”.

1. Giải thích vì sao gọi Instant.now() trực tiếp trong nhiều test có thể gây flaky.
2. Viết một test với Clock.fixed cho trước hạn một phút.
3. Viết một test khi đúng thời điểm hạn.
4. Triển khai constructor nhận Clock hoặc phương thức nhận now theo thiết kế hợp lý.
5. Phân tích mức độ phức tạp của việc tiêm phụ thuộc.
6. Tách việc **ra quyết định thời điểm** khỏi việc **gửi thông báo qua mạng**.

**Gợi ý:** ở thời điểm 09:00 UTC, hạn 09:01 chưa đến; hạn 09:00 đã đến theo quy tắc minh họa. Quy tắc thật cần thống nhất múi giờ và trường hợp cần nhắc bao nhiêu lần.

### 17.6. Nhiệm vụ E – Nêu giới hạn unit test (15 phút)

Giả sử hai request cùng đọc confirmed = 9 và capacity = 10.

Trả lời:
1. Vì sao canConfirm trả true ở cả hai request chưa đảm bảo dữ liệu cuối cùng đúng?
2. Ranh giới nào phải bảo vệ bất biến cập nhật?
3. Hãy đề xuất **một integration test** với database thật phù hợp cho trường hợp hai request tranh suất cuối.
4. Khi một request bị từ chối, trạng thái trả cho người dùng cần phản ánh điều gì?
5. Cần kiểm tra quyền xem thông tin đăng ký ở đâu?
6. Vì sao các test này bổ sung cho, không phủ nhận, unit-level TDD?

**Gợi ý:** chỉ unit test so sánh số nguyên không thể tạo transaction nguyên tử. Cần thiết kế và kiểm tra thao tác cập nhật phù hợp dữ liệu thực; cơ chế cụ thể tùy hạ tầng.

### 17.7. Nhiệm vụ F – Chọn test theo hành vi (10 phút)

Có hai đề xuất:
- **Test X:** “canConfirm(9,10) trả true”.
- **Test Y:** “phương thức private validateCounts được gọi đúng một lần”.

Hãy giải thích:
1. Test nào thường bền hơn khi refactor?
2. Trường hợp nào một tương tác cụ thể là hợp đồng cần kiểm tra?
3. Tại sao coverage cao không thay thế được test cho trường hợp concurrency?
4. Nếu test Y đỏ nhưng kết quả API không đổi, bạn sẽ xem lại điều gì?

### 17.8. Nhiệm vụ G – Lập kế hoạch học tập và cải tiến nhóm (15 phút)

Thiết kế một thử nghiệm trong **hai Sprint hoặc một khoảng Kanban tương đương**:
- Chọn một vùng mã nhỏ thường có lỗi, đủ điều kiện thử TDD.
- Thu baseline về lỗi, rework, thời gian hoàn tất và khả năng sửa đổi.
- Bắt đầu từ test hành vi, thực hiện Red–Green–Refactor.
- Tổ chức pairing hỗ trợ người mới khi cần.
- Đưa kiểm tra vào CI ở mức phù hợp.
- Ghi giới hạn: loại story, thay đổi năng lực, test mới mất thời gian ban đầu.
- Xem kết quả và quyết định giữ, điều chỉnh hoặc mở rộng thực hành.

**Tránh chỉ đặt mục tiêu tăng số test hoặc tăng velocity.** Hãy đo liệu nhóm giao tính năng có ích với ít rủi ro và ít việc sửa lại hơn không.

### 17.9. Thang tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Chu trình TDD** | Chỉ viết test sau code hoặc không chạy Red | Có Red đúng lý do, Green tối thiểu, Refactor | Chọn vòng nhỏ và giải thích tín hiệu thiết kế ở mỗi vòng |
| **Chất lượng test** | Test phụ thuộc chi tiết triển khai hoặc flaky | Test hành vi rõ, lặp được, có trường hợp biên | Chọn đúng tầng test, ranh giới mock và dữ liệu kiểm tra |
| **Thiết kế mã** | Tách lớp chỉ theo thói quen | API rõ, trách nhiệm gắn kết, phụ thuộc hợp lý | Cân bằng đơn giản với thay đổi thực và kiểm chứng refactor |
| **Giới hạn kỹ thuật** | Cho rằng unit test chứng minh mọi thứ | Nhận diện concurrency, database, quyền, người dùng | Có chiến lược kiểm tra bổ sung và rủi ro ưu tiên |
| **Agile và chất lượng** | Dùng test count làm KPI | Kết nối DoD, CI, giá trị user story | Đọc flow–quality–outcome với bối cảnh và cải tiến theo dữ liệu |

## 18. Biểu mẫu dùng trong thực hành

### 18.1. Phiếu lập một vòng Red – Green – Refactor

~~~text
Hành vi nhỏ cần bổ sung:
User story / vấn đề người dùng liên quan:
Test mới và tên test:
Dữ liệu Given:
Hành động When:
Kết quả Then:
Ở Red test thất bại vì:
Mã tối thiểu ở Green:
Các test liên quan đã chạy:
Điều cần Refactor:
Bằng chứng hành vi không đổi:
Rủi ro chưa được test ở cấp này:
Vòng tiếp theo cần học:
~~~

### 18.2. Phiếu nhận diện testability và thiết kế mã

~~~text
Đối tượng đang kiểm tra:
Trách nhiệm chính:
API mà người gọi thực sự cần:
Các phụ thuộc hiện có:
Phụ thuộc nào là chi tiết ngoại vi:
Đối tượng nào dễ kiểm tra bằng dữ liệu thuần:
Có cần tiêm phụ thuộc / interface không, vì sao:
Có trạng thái ẩn hoặc thời gian hệ thống không:
Có code lặp hoặc tên mơ hồ không:
Những test nào đang bám implementation:
Một refactoring nhỏ có thể thử:
Điều phải giữ nguyên theo hợp đồng:
~~~

### 18.3. Phiếu kiểm tra giới hạn và chiến lược test

~~~text
Quy tắc nghiệp vụ cần bảo vệ:
Unit test đang kiểm tra gì:
Component/service test cần gì:
Integration test cần gì:
Concurrency / transaction / retry cần xác minh gì:
Quyền truy cập và dữ liệu cần bảo vệ:
Acceptance criteria từ phía người dùng:
Điều kiện Definition of Done:
Điều unit test không thể chứng minh:
Ai cần review rủi ro và mốc kiểm tra:
~~~

### 18.4. Mẫu trao đổi sau một thử nghiệm TDD

~~~text
Vùng mã và loại công việc:
Vì sao thử TDD ở đây:
Baseline và hạn chế dữ liệu:
Số vòng hoặc trường hợp hành vi đã thực hiện:
Điểm thiết kế được làm rõ:
Phụ thuộc được giảm hoặc tăng:
Lỗi / rework / thời gian giao quan sát được:
Chất lượng CI và độ tin cậy test:
Người dùng có nhận lợi ích gì:
Điều chưa kết luận được:
Quyết định: tiếp tục / điều chỉnh / mở rộng / dừng thử:
Mốc kiểm tra lại:
~~~

Biểu mẫu chỉ nên được dùng khi giúp nhóm **học và ra quyết định**, không tạo thêm công việc giấy tờ cho mỗi vài dòng code.

## 19. Checklist trước khi coi một vòng TDD và thiết kế là hoàn tất

**Red – Green – Refactor:**

- [ ] Có một hành vi nhỏ, có ích và được hiểu đúng từ yêu cầu.
- [ ] Test mới được viết trước phần triển khai cần thiết.
- [ ] Test Red **thất bại đúng lý do**, không chỉ vì lỗi setup hoặc môi trường.
- [ ] Green dùng cách triển khai đơn giản đủ đáp ứng hành vi mới.
- [ ] Các test trước đó vẫn đạt sau bước Green.
- [ ] Refactor chỉ cải thiện cấu trúc, không lén thay đổi hành vi.
- [ ] Test được chạy lại sau refactor để bảo vệ hành vi.
- [ ] Khi test đã xanh sẵn, nhóm không cố phá mã mà chọn hành vi mới còn thiếu.

**Chất lượng thiết kế:**

- [ ] API dễ hiểu từ góc nhìn người gọi.
- [ ] Tên đối tượng/phương thức diễn đạt ngôn ngữ nghiệp vụ.
- [ ] Mỗi thành phần có trách nhiệm đủ rõ; tránh lớp ôm cả nghiệp vụ lẫn ngoại vi không cần thiết.
- [ ] Phụ thuộc được đưa qua ranh giới phù hợp khi có giá trị, không tạo interface hình thức.
- [ ] Test ưu tiên kết quả quan sát được, không khóa cấu trúc private.
- [ ] Không xây abstractions cho nhu cầu tương lai chưa có căn cứ.
- [ ] Refactoring nhỏ được hỗ trợ bởi test; test cũng được refactor khi khó đọc.

**Giới hạn và tích hợp:**

- [ ] Unit test không bị coi là bằng chứng đầy đủ cho transaction hoặc concurrency.
- [ ] Có kiểm thử tích hợp khi cần dữ liệu, network hoặc hợp đồng giữa thành phần.
- [ ] Quyền truy cập, dữ liệu cá nhân, trường hợp lỗi và retry được xem theo rủi ro.
- [ ] Test không phụ thuộc thời gian thật hoặc trạng thái chung một cách không kiểm soát.
- [ ] Các kiểm thử quan trọng được đưa vào CI và tín hiệu pipeline đáng tin.
- [ ] Acceptance criteria và Definition of Done được phân biệt, cùng được đáp ứng ở phạm vi phù hợp.
- [ ] Increment có ích được kiểm tra với người dùng; test xanh không đồng nghĩa Product Goal đã đạt.
- [ ] Việc cải tiến được đánh giá bằng flow, chất lượng và kết quả sản phẩm, không chỉ test count hoặc coverage.

**Kết luận:** TDD hữu ích nhất khi được thực hành như **một vòng phản hồi về cả hành vi lẫn thiết kế mã**. **Red** làm rõ điều còn thiếu; **Green** giúp tạo hành vi đơn giản; **Refactor** biến sự an tâm từ kiểm thử thành cơ hội giảm trùng lặp, cải thiện ranh giới và giữ mã dễ thay đổi. Khi kết hợp với integration tests, CI, pairing, Definition of Done và phản hồi người dùng, TDD hỗ trợ mục tiêu Agile: **giao phần mềm có giá trị theo từng bước nhỏ, phát hiện sai lệch sớm và duy trì khả năng thích ứng mà không đánh đổi chất lượng**.

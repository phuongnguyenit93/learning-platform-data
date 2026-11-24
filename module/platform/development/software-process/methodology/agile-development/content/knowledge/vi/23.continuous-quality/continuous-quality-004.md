# Tổ chức kiểm thử theo nhiều mức cùng vòng phản hồi phù hợp

> **Ý chính:** Chất lượng liên tục trong Agile không đạt được bằng cách đợi đến cuối Sprint rồi chạy một bộ kiểm thử thật lớn. Một chiến lược hiệu quả kết hợp **nhiều mức kiểm thử**, chọn **mức gần nhất vẫn đủ bằng chứng** cho từng rủi ro, và đặt phản hồi ở **thời điểm người nhận còn có thể sửa sai với chi phí hợp lý**. Unit tests, component tests, contract tests, integration tests, end-to-end tests, kiểm thử khám phá và quan sát production cần **bổ trợ nhau**, không sao chép cùng một kịch bản trên mọi tầng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích tại sao **kiểm thử nhiều mức** và **vòng phản hồi ngắn** cùng góp phần tạo Increment đáng tin, thay vì chỉ gia tăng số test.
2. Phân biệt **static checks, unit, component, contract, integration, end-to-end, exploratory testing** và các kiểm tra thuộc tính chất lượng như bảo mật, hiệu năng, khả năng tiếp cận.
3. Chọn cấp kiểm thử dựa trên **rủi ro, ranh giới cần quan sát, độ nhanh, độ ổn định, khả năng chẩn đoán và chi phí bảo trì**.
4. Thiết kế vòng phản hồi từ **trước khi code → máy Developer → pull request/CI → tích hợp → phát hành → sử dụng thực**, với chính sách chất lượng rõ ở mỗi điểm.
5. Dùng **TDD, BDD, ATDD, Definition of Done và acceptance criteria** đúng vai trò, tránh nhầm phương pháp phát triển với cấp kiểm thử.
6. Nhận diện và xử lý **flaky tests, bộ test quá chậm, môi trường thiếu đại diện, dữ liệu thử không ổn định, sự trùng lặp và test bám chi tiết triển khai**.
7. Lập chiến lược kiểm thử cho một luồng phần mềm có API, cơ sở dữ liệu, UI và phụ thuộc dịch vụ bên ngoài.
8. Đánh giá hiệu quả bằng **tín hiệu chất lượng, tốc độ phản hồi, dòng công việc và outcome người dùng**, không biến coverage hoặc số lượng test thành mục tiêu tự thân.

## 2. Mở đầu: vì sao “mọi test đều để cuối Sprint” nguy hiểm?

Một Scrum Team phát triển nền tảng học trực tuyến. Product Owner ưu tiên chức năng giúp người học lưu tiến độ để tiếp tục bài sau khi chuyển thiết bị hoặc gặp gián đoạn mạng.

Nhóm triển khai:

- Frontend hiển thị thông báo đã lưu.
- API nhận yêu cầu cập nhật tiến độ.
- Database ghi vị trí bài học.
- Một dịch vụ định danh kiểm tra quyền truy cập.

Từng Developer kiểm tra phần của mình bằng tay. Đến cuối Sprint mới chạy thử từ UI tới database. Khi đó phát hiện:

- API chấp nhận dữ liệu nhưng UI báo thành công **trước khi** có xác nhận lưu.
- Trường hợp mất phản hồi khiến người học không biết đã lưu hay chưa.
- Người không có quyền có thể yêu cầu đọc dữ liệu tiến độ của người khác trong một tình huống biên.
- Thay đổi schema làm một luồng cũ không còn hoạt động.

Lỗi xuất hiện ở nhiều lớp. Để sửa, nhóm phải quay lại quyết định nghiệp vụ, code giao diện, hợp đồng API, cách lưu và cấu hình môi trường. Thời gian tìm nguyên nhân tăng lên vì các thay đổi đã tích lũy trong nhiều ngày.

**Không phải mọi lỗi đều có thể ngăn ngay ở unit test.** Nhưng nếu nhóm đặt kiểm tra phù hợp ở những ranh giới quan trọng và chạy đủ sớm, nhiều vấn đề sẽ không phải chờ tới cuối Sprint mới được biết.

> Câu hỏi thiết kế chiến lược không phải “Làm sao thêm nhiều test nhất?”, mà là **“Rủi ro nào cần biết sớm ở cấp nào, ai cần nhận kết quả và hành động gì khi kiểm tra thất bại?”**

## 3. Một mô hình tư duy: rủi ro – mức kiểm tra – thời điểm phản hồi

### 3.1. Ba trục cần xem đồng thời

| Trục | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Rủi ro / hành vi** | Sai điều gì sẽ làm người dùng mất giá trị hoặc tổ chức bị ảnh hưởng? | Báo lưu thành công giả, truy cập sai dữ liệu |
| **Mức kiểm thử** | Phải kiểm tra qua những ranh giới nào mới có bằng chứng đáng tin? | Hàm, dịch vụ, API–database, toàn hành trình |
| **Vòng phản hồi** | Khi nào cần nhận kết quả để sửa trước khi lỗi lan rộng? | Lúc code, trong CI, trước phát hành, sau rollout |

Ba trục **không trùng nhau**. Một contract test có thể chạy ở máy Developer và trong CI. Một E2E test có thể chạy trong pipeline trước phát hành và sau triển khai ở môi trường thích hợp. Một unit test có thể được tạo bằng TDD hoặc viết sau khi sửa lỗi hồi quy.

### 3.2. Mô hình phản hồi nhiều lớp

~~~mermaid
flowchart TD
    P["Product Goal và vấn đề người dùng"] --> D["Ví dụ nghiệp vụ / acceptance criteria"]
    D --> U["Phản hồi nhanh: static checks, unit/component"]
    U --> C["Phản hồi ranh giới: contract, integration"]
    C --> E["Phản hồi hành trình: E2E chọn lọc, exploratory"]
    E --> Q{"Đạt Definition of Done và điều kiện phát hành?"}
    Q -->|"Chưa"| F["Làm rõ lỗi, sửa tại nguồn, chạy lại kiểm tra"]
    F --> U
    Q -->|"Có"| I["Increment tích hợp, phát hành có kiểm soát"]
    I --> O["Quan sát production và phản hồi người dùng"]
    O --> P
~~~

Sơ đồ không ngụ ý mọi thay đổi phải đi qua đúng một đường thẳng. Trong thực tế, khi có lỗi E2E, nhóm nên **đưa kiểm tra về mức nhỏ hơn nếu có thể** để phát hiện lỗi tương tự nhanh và ổn định hơn lần sau.

### 3.3. Mục đích của nhiều tầng không phải “kiểm tra đi kiểm tra lại”

Xem cùng một quy tắc **không báo “Đã lưu” nếu backend chưa xác nhận**:

- **Unit:** quyết định trạng thái của một service có đúng khi nhận kết quả thất bại?
- **Contract:** ý nghĩa của mã/trường phản hồi API có thống nhất giữa UI và backend không?
- **Integration:** thao tác với database lỗi thật có được chuyển tới API chính xác không?
- **E2E:** người học thực sự nhìn thấy trạng thái phù hợp qua giao diện không?
- **Production observation:** dưới mạng và thiết bị thực tế có xuất hiện thông báo sai hoặc mất tiến độ không?

Những câu hỏi này **có liên quan nhưng không giống nhau**. Trùng lặp có chủ đích ở hành trình rủi ro cao có thể hữu ích; nhân bản hàng trăm kịch bản UI để kiểm tra từng nhánh logic đơn giản thường làm hệ thống test chậm và giòn.

## 4. Bản đồ các mức kiểm thử

### 4.1. Bảng phân biệt trọng tâm

| Mức / loại | Ranh giới được kiểm tra | Rủi ro chính có thể phát hiện | Tốc độ thường gặp | Điều không tự chứng minh |
|---|---|---|---|---|
| **Static checks** | Mã/kiểu/cấu hình, chưa cần chạy ứng dụng đầy đủ | Sai kiểu, quy ước, một số mẫu lỗi và cấu hình nguy hiểm | Thường nhanh | Hành vi chạy thật và giá trị nghiệp vụ |
| **Unit test** | Quy tắc nhỏ trong một đơn vị code, phụ thuộc có thể thay bằng test double | Điều kiện, tính toán, chuyển trạng thái | Thường rất nhanh | Hợp đồng giữa dịch vụ và môi trường thật |
| **Component/service test** | Một thành phần hoặc dịch vụ với giao diện công khai | Hành vi cấp dịch vụ, phối hợp một số phần bên trong | Nhanh đến vừa | Toàn hệ thống hoặc bên ngoài thật |
| **Contract test** | Kỳ vọng giữa bên cung cấp và bên sử dụng interface/API | Thay đổi schema, kiểu, trường, quy tắc giao tiếp | Nhanh đến vừa tùy thiết lập | Toàn luồng nghiệp vụ chạy thành công |
| **Integration test** | Hai hay nhiều phần thực tương tác: API–DB, service–queue, adapter–dependency | Lỗi kết nối, ánh xạ, giao dịch, cấu hình, dữ liệu | Vừa tới chậm hơn | Hành trình người dùng cuối hoàn chỉnh |
| **End-to-end (E2E)** | Một hành trình quan trọng qua nhiều thành phần, thường từ UI | Lỗi liên kết ở góc nhìn sử dụng, điều hướng, xử lý lỗi thực tế | Thường chậm và nhạy môi trường hơn | Mọi nhánh logic, mọi thiết bị và outcome |
| **Exploratory test** | Người kiểm thử chủ động khám phá và điều chỉnh thử nghiệm | Trường hợp lạ, hiểu sai, bất tiện, hành vi ngoài kịch bản | Phụ thuộc phạm vi | Bộ hồi quy tự động chạy đều về sau |
| **Kiểm tra thuộc tính chất lượng** | Bảo mật, hiệu năng, độ bền, khả năng tiếp cận... ở tầng phù hợp | Rủi ro phi chức năng hoặc xuyên suốt | Rất khác nhau | Không có một công cụ đơn lẻ bao phủ toàn bộ |
| **Quan sát sản phẩm thực** | Telemetry, logs, metrics, traces, phản hồi người dùng | Sai lệch khi sử dụng, tải và dữ liệu thực | Liên tục hoặc theo đợt | Không thay thế bảo vệ trước khi phát hành |

Tốc độ là xu hướng, **không phải luật cố định**: một integration test nhỏ trên database tạm có thể nhanh hơn một unit test nặng mock; một E2E test có thể chạy ổn nếu môi trường được quản lý kỹ.

### 4.2. Static checks: tìm lỗi trước khi chạy

Ví dụ:

- **Biên dịch/type checking** phát hiện gọi sai interface hoặc truyền sai kiểu.
- **Formatter/linter** giúp giữ cách viết nhất quán và cảnh báo những mẫu code đáng ngờ.
- **Static analysis** tìm một số rủi ro bảo mật hoặc chất lượng.
- **Dependency/secret scanning** hỗ trợ phát hiện thư viện có vấn đề hoặc bí mật vô tình đưa vào repository.

**Giới hạn:** type check xanh không bảo đảm người học được lưu tiến độ đúng; secret scanning không thay thế chiến lược bảo mật hoặc kiểm thử quyền truy cập. Cần phản ứng theo mức nghiêm trọng của kết quả, tránh làm ngơ cảnh báo quan trọng lặp lại.

### 4.3. Unit tests: phản hồi về quy tắc nhỏ

Một unit test tốt nên:

- Có đầu vào và kết quả được diễn đạt rõ.
- Chạy đủ nhanh để Developer dùng thường xuyên.
- Không phụ thuộc thời gian thực, thứ tự test, mạng hoặc database thật nếu không cần.
- Tập trung vào **hành vi cần giữ**, không khóa mọi bước triển khai.
- Khi thất bại, giúp xác định nguyên nhân tương đối nhanh.

Ví dụ: khi repository báo lưu thất bại, hàm chuyển kết quả phải trả trạng thái **FAILED**, không được trả **CONFIRMED**.

Không phải mọi class phải có một file test riêng. Độ bao phủ cần bám **rủi ro và hành vi**, không chỉ cấu trúc thư mục của mã nguồn.

### 4.4. Component tests: kiểm tra hành vi một thành phần

Một component test có thể khởi tạo service cùng các collaborator nội bộ, thay adapter ngoài bằng giả lập có kiểm soát và gọi **public interface** để xác minh hành vi.

Ví dụ: gọi endpoint ở một component backend với kho dữ liệu giả, xác nhận phản hồi và validation. Nó bao phủ nhiều phần hơn unit test, nhưng vẫn nhanh nếu không cần toàn bộ hệ thống.

**Lưu ý:** các đội không phải lúc nào cũng đặt tên unit/component/service test giống nhau. Hãy ghi rõ **phần nào là thật, phần nào là test double và ranh giới nào được xác nhận** thay vì tranh luận nhãn.

### 4.5. Contract tests: giữ thỏa thuận giữa các bên

Khi UI và API hoặc hai dịch vụ phát triển độc lập, lỗi có thể không nằm trong nội bộ từng bên. Ví dụ UI hiểu **status = SAVED** là đã ghi bền vững, còn API dùng nó để nói **request đã được nhận**.

Contract test có thể xác minh:

- Cấu trúc và kiểu dữ liệu request/response.
- Những trường bắt buộc, giá trị có thể trả và cách version.
- Ý nghĩa các trạng thái lỗi quan trọng.
- Tính tương thích giữa bên cung cấp và bên sử dụng trong phạm vi đã thỏa thuận.

Có thể dùng **schema-based contract testing** hoặc **consumer-driven contract testing** khi phù hợp. Một hợp đồng đã xác minh **không tự bảo đảm toàn bộ nghiệp vụ**: hai bên có thể tuân thủ đúng schema nhưng lưu tiến độ sai vì quy tắc nội bộ.

### 4.6. Integration tests: kiểm chứng các phần hoạt động cùng nhau

Ví dụ:

- Backend thật gọi database thử để ghi/đọc tiến độ.
- Service phát event vào message broker và consumer xử lý đúng.
- API tương tác với hệ thống định danh trong môi trường kiểm thử.
- Migration database tương thích với các truy vấn thiết yếu.

Integration tests rất quan trọng với **giao dịch, serialization, cấu hình, permission và xử lý lỗi dependency**. Tuy nhiên, nếu chúng yêu cầu tài khoản dùng chung và dữ liệu không thể làm sạch, bộ test có thể trở nên khó chạy và không ổn định.

Để tăng độ tin cậy, ưu tiên dữ liệu riêng, môi trường cô lập, cleanup có kiểm soát, phiên bản dependency rõ và kết quả có thể tái hiện.

### 4.7. End-to-end: kiểm tra ít hành trình, nhưng thật sự quan trọng

E2E thường giúp trả lời các câu hỏi như:

- Người học có thể đăng nhập, mở bài, lưu rồi mở lại không?
- Thông điệp thất bại có được thể hiện đúng khi API trả lỗi không?
- Một tính năng hoạt động ở backend nhưng chưa nối đúng giao diện có bị phát hiện không?

**Không nên tạo một E2E test cho từng phép tính nhỏ**. Dùng unit/component tests cho nhiều quy tắc; dành E2E cho những hành trình có giá trị cao hoặc rủi ro liên kết mà tầng thấp khó chứng minh.

E2E không bắt buộc phải đi qua **mọi** hệ thống ngoài; có thể thay một dịch vụ không ổn định bằng stub có hợp đồng đáng tin trong một phần kiểm tra, rồi bổ sung integration/contract test riêng với dịch vụ thực.

## 5. Ví dụ cụ thể: cùng một quy tắc, nhiều mức phản hồi

### 5.1. Quy tắc nghiệp vụ cần bảo vệ

> “Ứng dụng chỉ báo tiến độ đã được lưu khi có xác nhận lưu hợp lệ; khi thất bại hoặc chưa xác định kết quả thì không được thông báo thành công giả.”

Trước khi viết test, nhóm làm rõ:

1. Thế nào là **xác nhận hợp lệ**?
2. Những trạng thái nào có thể xảy ra: **CONFIRMED, FAILED, UNKNOWN**?
3. Khi timeout, có được thử lại? Nếu có, xử lý idempotency và đối soát ra sao?
4. Người học nhìn thấy gì, có thể tiếp tục thao tác nào?
5. Những chính sách nào thuộc phạm vi của lát cắt đang thực hiện?

Không tự viết cơ chế thử lại có thể làm mất dữ liệu hoặc tạo ghi trùng nếu các điều kiện này chưa được xác nhận.

### 5.2. Unit test Java/JUnit 5 minh họa

Thiết kế một lớp chuyển kết quả kỹ thuật thành trạng thái nghiệp vụ. Đoạn code sau là **ví dụ độc lập cho một quy tắc**, chưa phải API lưu dữ liệu thật.

~~~java
enum RepositoryOutcome {
    STORED, REJECTED, NO_RELIABLE_RESPONSE
}

enum SaveStatus {
    CONFIRMED, FAILED, UNKNOWN
}

final class SaveStatusMapper {
    SaveStatus map(RepositoryOutcome outcome) {
        return switch (outcome) {
            case STORED -> SaveStatus.CONFIRMED;
            case REJECTED -> SaveStatus.FAILED;
            case NO_RELIABLE_RESPONSE -> SaveStatus.UNKNOWN;
        };
    }
}
~~~

Một số unit tests:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class SaveStatusMapperTest {
    private final SaveStatusMapper mapper = new SaveStatusMapper();

    @Test
    void confirmsOnlyAfterStoredOutcome() {
        assertEquals(
            SaveStatus.CONFIRMED,
            mapper.map(RepositoryOutcome.STORED)
        );
    }

    @Test
    void failureMustNotLookLikeSuccess() {
        assertEquals(
            SaveStatus.FAILED,
            mapper.map(RepositoryOutcome.REJECTED)
        );
    }

    @Test
    void missingResponseIsNotConfirmed() {
        assertEquals(
            SaveStatus.UNKNOWN,
            mapper.map(RepositoryOutcome.NO_RELIABLE_RESPONSE)
        );
    }
}
~~~

Đoạn mã dùng **switch expression của Java hiện đại**. Nếu dự án dùng phiên bản Java khác, cú pháp cần điều chỉnh. Không có triển khai kho dữ liệu ở đây; vì vậy test chỉ chứng minh **ánh xạ ba trạng thái**, không chứng minh database đã lưu hoặc UI đã phản hồi chính xác.

### 5.3. Contract test tại ranh giới UI–API

Một ví dụ hợp đồng **minh họa, không phải chuẩn HTTP bắt buộc**:

~~~json
{
  "saveStatus": "UNKNOWN",
  "messageCode": "SAVE_RESULT_UNAVAILABLE",
  "progressVersion": null
}
~~~

Các câu hỏi contract test:

- Khi API chưa đủ bằng chứng xác nhận, trường **saveStatus** có được phép là **CONFIRMED** không? **Không** theo quy tắc này.
- UI có biết xử lý **UNKNOWN** mà không hiển thị thông báo thành công sai không?
- Các trường bắt buộc có nhất quán với version API và consumer hiện tại không?
- Nếu thêm trạng thái mới, consumer có phản ứng an toàn thay vì mặc định coi là thành công không?

Contract test phải bảo đảm **ý nghĩa được các bên thống nhất**, không chỉ schema có chứa chuỗi hợp lệ.

### 5.4. Integration test với nơi lưu thật trong môi trường thử

Một trường hợp tích hợp:

~~~text
Given:
  Tạo người học thử có quyền và tiến độ ban đầu ở phút 3.

When:
  Gửi yêu cầu lưu phút 5 qua API thật với database thử.

Then:
  API chỉ báo CONFIRMED sau khi dữ liệu đáp ứng điều kiện xác nhận.
  Đọc lại tiến độ trả phút 5 theo quy tắc sản phẩm.

And:
  Với lỗi ghi được chủ động tạo trong môi trường thử,
  API không báo CONFIRMED.

Cleanup:
  Xóa dữ liệu thử hoặc hủy giao dịch theo cơ chế môi trường.
~~~

Test này kiểm tra **sự phối hợp API–database**, nhưng chưa xác nhận người học thấy thông điệp đúng trên giao diện.

### 5.5. Acceptance/E2E test cho một hành trình quan trọng

~~~gherkin
Feature: Lưu và mở lại tiến độ học

  Scenario: Người học lưu thành công và tiếp tục bài
    Given người học có quyền truy cập bài "Java cơ bản"
    And bài học đang có tiến độ ở phút thứ 3
    When người học tiếp tục đến phút thứ 5
    And hệ thống xác nhận đã lưu tiến độ
    Then người học nhìn thấy trạng thái "Đã lưu"
    And khi mở lại bài thì tiến độ được khôi phục theo quy tắc sản phẩm

  Scenario: Lưu thất bại không bị thông báo thành công
    Given người học đang có tiến độ chưa được xác nhận
    When người học yêu cầu lưu
    And dịch vụ lưu trả lỗi
    Then giao diện không thông báo "Đã lưu"
    And người học thấy trạng thái và hướng xử lý phù hợp
~~~

Các bước Gherkin dùng từ khóa tiếng Anh với nội dung tiếng Việt. Để chạy tự động cần **step definitions**, thiết lập dữ liệu và môi trường thử; file scenario tự nó **không phải bài kiểm thử đã thực thi**.

### 5.6. Lỗi nào thuộc mức nào?

| Lỗi giả định | Mức giúp phát hiện sớm | Vì sao? |
|---|---|---|
| Chuyển **REJECTED** thành **CONFIRMED** | Unit | Sai logic ánh xạ nhỏ |
| Backend đổi tên trường **saveStatus** | Contract | Consumer phụ thuộc cấu trúc API |
| Ghi database thất bại vì migration không phù hợp | Integration | Cần tương tác thật với schema và truy vấn |
| UI luôn hiện toast xanh dù API báo FAILED | Component UI hoặc E2E chọn lọc | Cần kiểm tra liên kết trạng thái tới hiển thị |
| Người học không hiểu trạng thái UNKNOWN | Exploratory/UX test | Vấn đề hiểu và trải nghiệm |
| Lỗi chỉ xuất hiện trên thiết bị/mạng đặc thù | Kiểm tra thiết bị phù hợp và quan sát thực | Cần điều kiện tương ứng |

**Tư duy tối ưu:** khi một E2E test phát hiện lỗi logic ánh xạ, thêm unit test cho nguyên nhân ở mức nhỏ để lần sau phản hồi sớm; vẫn giữ đủ E2E test để bảo vệ luồng người dùng.

## 6. Tổ chức vòng phản hồi theo thời điểm

### 6.1. Từ lúc hiểu yêu cầu tới khi người dùng sử dụng

| Thời điểm | Loại phản hồi ưu tiên | Người cần phản ứng | Quyết định có thể đưa ra |
|---|---|---|---|
| **Discovery / refinement** | Ví dụ nghiệp vụ, phản ví dụ, acceptance criteria, rủi ro | Product Owner, Developers, Tester, chuyên gia | Xác nhận phạm vi, chia nhỏ PBI, làm rõ điều chưa biết |
| **Khi viết code trên máy Developer** | Type/lint, unit tests, component tests nhanh, TDD | Developer và người pairing | Sửa logic/thiết kế ngay |
| **Pull request / CI** | Build, static checks, unit/component, contract/integration trọng yếu, review | Developers và người liên quan | Chặn hoặc sửa thay đổi chưa đủ điều kiện |
| **Tích hợp trên nhánh chung** | Hợp đồng giữa services, tích hợp dữ liệu, smoke, kiểm tra hồi quy | Scrum Team/kỹ sư liên quan | Khôi phục trạng thái tích hợp đáng tin |
| **Trước phát hành** | E2E quan trọng, security/performance/operational readiness theo rủi ro | Developers, vận hành, người có thẩm quyền khi cần | Phát hành, thu hẹp phạm vi hoặc hoãn |
| **Sau phát hành** | Logs/metrics/traces, synthetic checks, phản hồi người dùng, outcome | Scrum Team, vận hành, Product Owner | Ứng cứu, rollback, cập nhật Product Backlog |

Không có quy định **mọi bộ test chỉ được chạy ở đúng một thời điểm**. Một số bài kiểm tra quan trọng nên chạy lặp ở nhiều điểm; chính sách cụ thể tùy chi phí và mức nguy hại nếu lỗi lọt tới người dùng.

### 6.2. Vòng phản hồi càng gần nguồn càng dễ sửa

Một sai điều kiện phát hiện khi viết unit test thường dễ chẩn đoán hơn cùng lỗi phát hiện từ browser E2E sau ba tuần tích hợp. Nhưng rút ngắn phản hồi **không có nghĩa dời toàn bộ kiểm thử sang unit level**.

Mục tiêu là tìm **điểm sớm nhất có đủ bằng chứng**:

- Sai kiểu, sai format → biên dịch/static checks.
- Sai phép tính/quy tắc cục bộ → unit test.
- Sai hợp đồng API → contract test.
- Sai phối hợp với DB/queue → integration test.
- Sai trải nghiệm đầu–cuối → E2E/khám phá.
- Sai dưới điều kiện tải và dữ liệu thực → performance/resilience tests và quan sát.

### 6.3. Phản hồi nhanh phải đáng tin

Một pipeline trả kết quả trong hai phút nhưng thường **xanh giả** không hữu ích. Một bộ test đầy đủ nhưng chạy ba giờ ở mỗi commit cũng có thể làm nhóm ngừng dùng nó.

Khi tổ chức vòng phản hồi cần cân bằng:

1. **Độ phát hiện:** lỗi quan trọng nào có thể được nhìn thấy?
2. **Độ trễ:** phải chờ bao lâu?
3. **Độ ổn định:** test có thường thất bại vì điều kiện không liên quan code không?
4. **Khả năng chẩn đoán:** lỗi chỉ vào quy tắc cụ thể hay báo đỏ chung chung?
5. **Chi phí duy trì:** test có bị vỡ chỉ vì thay đổi chi tiết nội bộ không?
6. **Rủi ro khi chưa chạy:** có điều kiện bắt buộc nào không được trì hoãn?

Vì thế, test nhanh và test sâu **bổ sung nhau**, không đơn thuần xếp hạng “nhanh là tốt hơn”.

## 7. Xây một pipeline kiểm thử nhiều tầng

### 7.1. Ví dụ pipeline có phản hồi theo rủi ro

~~~yaml
# Pseudocode YAML minh họa, không gắn với một CI provider.
on_local_change:
  - compile
  - static_checks
  - fast_unit_and_component_tests

on_pull_request:
  - compile_and_static_analysis
  - unit_and_component_tests
  - critical_contract_tests
  - selected_integration_tests
  - review_and_security_checks_as_required

on_mainline:
  - integration_and_database_migration_tests
  - smoke_tests_of_integrated_build
  - regression_checks_appropriate_to_risk

before_release:
  - critical_user_journey_e2e_tests
  - access_control_and_security_validation
  - performance_or_resilience_checks_when_required
  - operational_readiness_and_release_criteria

after_release:
  - deployment_smoke_checks
  - telemetry_and_error_monitoring
  - feedback_and_outcome_review
  - rollback_or_mitigation_when_thresholds_require
~~~

Đây là **gợi ý tổ chức**, không phải danh sách công cụ hay thời lượng chuẩn. Một kiểm soát bảo mật quan trọng không nên chỉ chạy “khi nào tiện”; nếu nó là điều kiện bắt buộc trước merge hoặc release, pipeline phải phản ánh đúng.

### 7.2. Chiến lược chạy nhanh và chuyên sâu

**Luồng nhanh** có thể gồm compile, lint, unit tests và component/contract tests thiết yếu. Chúng trả kết quả thường xuyên khi Developers viết code.

**Luồng sâu** có thể gồm integration tests tốn thời gian, E2E hồi quy chọn lọc, kiểm tra hiệu năng và khả năng phục hồi. Nên chạy tại những thời điểm phù hợp với chi phí và mức rủi ro, nhưng **trước khi hành động nguy hiểm được cho phép** nếu chúng là điều kiện bắt buộc.

Những lần chạy theo lịch có thể mở rộng độ bao phủ nhưng **không thay thế gate bắt buộc**. Nếu chỉ phát hiện một lỗi thanh toán nghiêm trọng vào sáng hôm sau khi chức năng đã phát hành, nhịp kiểm tra đó không đáp ứng yêu cầu an toàn của sản phẩm.

### 7.3. Ví dụ “chọn test theo thay đổi” cần thận trọng

Một thay đổi chỉ liên quan phần giao diện màu sắc có thể không cần chạy đầy đủ bộ thử tải mỗi lần. Nhưng hệ thống xác định vùng ảnh hưởng có thể bỏ sót ràng buộc gián tiếp. Vì vậy:

- Có một **bộ test cốt lõi** chạy cho mọi thay đổi quan trọng.
- Khi dùng **test impact analysis**, quy tắc chọn test phải minh bạch và được xác nhận định kỳ.
- Những thay đổi ảnh hưởng quyền truy cập, thanh toán, dữ liệu hoặc schema thường cần kiểm tra sâu hơn.
- Vẫn chạy bộ kiểm tra hồi quy diện rộng ở nhịp phù hợp để phát hiện thiếu sót của cơ chế chọn.

Không tối ưu vài phút CI bằng cách âm thầm bỏ qua tín hiệu chất lượng cần thiết.

### 7.4. Phân biệt build, merge, release và rollout

- **Build thành công:** mã biên dịch/đóng gói theo điều kiện đã đặt.
- **Test đạt:** những kiểm tra đã chạy thành công trong điều kiện xác định.
- **Merge/integrate:** thay đổi tham gia codebase/hệ thống chung.
- **Increment đạt DoD:** phần sản phẩm tích hợp đáp ứng chuẩn chất lượng của Scrum Team/sản phẩm.
- **Release/deploy:** phần thay đổi được đưa tới môi trường hay người dùng theo quy trình.
- **Rollout:** mức độ người dùng được kích hoạt phần thay đổi có thể được điều chỉnh.
- **Outcome đạt:** bằng chứng người dùng/sản phẩm thực sự tiến gần mục tiêu.

Không được đồng nhất các khái niệm trên. **CI xanh không tự bảo đảm Increment đạt DoD** nếu còn điều kiện quan trọng ngoài pipeline.

## 8. Các thuộc tính chất lượng cần kiểm tra xuyên nhiều mức

Một sản phẩm có thể **đúng chức năng** nhưng vẫn không an toàn, chậm, khó tiếp cận hoặc không thể phục hồi khi gặp sự cố. Vì vậy, chiến lược nhiều mức không chỉ gồm unit–integration–E2E cho happy path.

### 8.1. Bảo mật và quyền truy cập

Với nền tảng học, kiểm tra bảo mật có thể bao gồm:

- **Static/dependency/secret checks:** phát hiện cấu hình hoặc phụ thuộc đáng ngờ sớm.
- **Unit/component:** xác minh quy tắc kiểm soát quyền trong những thành phần quan trọng.
- **API/integration:** xác minh người học A không đọc hoặc sửa tiến độ thuộc người học B khi thiếu quyền.
- **Security testing theo rủi ro:** xác minh phiên, giới hạn truy cập, cấu hình và luồng xử lý dữ liệu trong môi trường phù hợp.
- **Production:** quan sát truy cập bất thường với dữ liệu tối thiểu, kiểm soát quyền xem log theo chính sách.

Không có một test tự động nào bảo đảm sản phẩm “an toàn tuyệt đối”. Các kiểm tra cần bám **mô hình đe dọa, dữ liệu được bảo vệ và yêu cầu tuân thủ**; thay đổi quan trọng có thể cần chuyên gia hoặc thẩm quyền phê duyệt.

### 8.2. Hiệu năng và khả năng chịu tải

Một unit test có thể xác nhận phép tính trong vài mili giây nhưng không biết điều gì xảy ra khi hàng nghìn người học cùng lưu tiến độ.

Các mức kiểm tra:

- **Microbenchmark** khi tối ưu logic cụ thể, có kiểm soát nhiễu đo.
- **Component/integration performance tests** cho truy vấn, kết nối và đường đi dữ liệu.
- **Load tests** ở môi trường đủ đại diện để xem độ trễ, thông lượng, mức lỗi theo tải.
- **Stress/resilience tests** theo rủi ro để xem hành vi khi dependency chậm, không khả dụng hoặc tài nguyên cạn.
- **Production monitoring** đo độ trễ và lỗi theo phân khúc, tránh chỉ nhìn trung bình.

Hiệu năng phải gắn **người dùng và mục tiêu dịch vụ**. Đừng lấy một benchmark trong máy Developer làm bảo đảm về production.

### 8.3. Khả năng tiếp cận và trải nghiệm người dùng

Kiểm tra tự động có thể bắt một phần lỗi HTML, nhãn điều khiển hoặc tương phản; nhưng không đủ để khẳng định người dùng công nghệ hỗ trợ có thể hoàn thành tác vụ.

Một chiến lược thực dụng:

- Dùng static/a11y checks cho vấn đề cơ bản.
- Kiểm tra tương tác bàn phím và trạng thái focus ở cấp component/UI.
- Thử hành trình quan trọng với công nghệ hỗ trợ trong phạm vi phù hợp.
- Quan sát người dùng, phỏng vấn hoặc exploratory testing để kiểm tra ngôn ngữ, thông điệp lỗi và khả năng hoàn thành.

Một thông báo “Lưu thất bại” có thể đúng theo backend nhưng khó hiểu hoặc không được đọc bởi screen reader. **Kiểm thử đúng giao thức không đồng nghĩa đúng trải nghiệm.**

### 8.4. Khả năng phục hồi và tính nhất quán dữ liệu

Các kiểm tra liên quan:

| Rủi ro | Mức kiểm tra nên cân nhắc | Ví dụ |
|---|---|---|
| Timeout giữa yêu cầu và phản hồi | Component/contract/integration | Không tự kết luận lưu thất bại hay thành công nếu chưa có bằng chứng |
| Gửi lặp do người dùng thử lại | Unit/integration | Hành vi idempotency hoặc đối soát theo chính sách nghiệp vụ |
| Database restart giữa giao dịch | Integration/resilience | Hành vi giao dịch và phục hồi phù hợp |
| Event đến lặp hoặc sai thứ tự | Component/integration | Consumer xử lý lặp và thứ tự theo hợp đồng |
| Migration dữ liệu không tương thích | Migration/integration test | Phiên bản mới đọc/ghi đúng dữ liệu đủ điều kiện |
| Rollback sau lỗi phát hành | Kiểm tra triển khai/khôi phục | Có thể trở về trạng thái an toàn theo chính sách |

**Không tự thêm retry vào mọi lỗi.** Với thanh toán, ghi dữ liệu hoặc xử lý tác vụ có tác dụng phụ, thử lại thiếu quy tắc có thể khiến sai lệch trầm trọng hơn.

### 8.5. Kiểm thử khám phá tìm điều chưa được viết thành kịch bản

**Exploratory testing** kết hợp việc học về hệ thống, thiết kế thử và thực hiện kiểm tra trong cùng một hoạt động. Nó đặc biệt có ích khi:

- Hành vi nghiệp vụ còn nhiều ngoại lệ chưa biết.
- Giao diện có nhiều cách người dùng tương tác.
- Điều kiện mạng, thiết bị hoặc trình duyệt đa dạng.
- Các thay đổi liên quan trải nghiệm và thông báo lỗi.

Ví dụ một phiên khám phá **30 phút minh họa**:

1. Mục tiêu: tìm tình huống “UI báo đã lưu nhưng dữ liệu không đúng”.
2. Phạm vi: một bài học, người dùng thử, mạng gián đoạn, thao tác mở lại.
3. Hành động: ngắt mạng trước và sau khi gửi, làm mới trang, bấm lặp, chuyển tab.
4. Ghi nhận: bước tái hiện, trạng thái quan sát, dữ liệu được ẩn danh.
5. Quyết định: lỗi cần sửa, ví dụ nghiệp vụ cần làm rõ, bài test hồi quy nào nên được tự động hóa.

**Không biến exploratory testing thành click ngẫu nhiên không có mục tiêu**, cũng không dùng tự động hóa để loại bỏ hoàn toàn kiểm thử khám phá.

## 9. Độ tin cậy của test: tránh phản hồi giả và hàng chờ kiểm thử

### 9.1. Flaky test là gì?

**Flaky test** là bài test đôi khi qua, đôi khi thất bại **không tương ứng đáng tin cậy với thay đổi hành vi của code** trong những điều kiện được xem là tương đương.

Nguyên nhân thường gặp:

- Race condition và xử lý bất đồng bộ chưa chờ đúng tín hiệu.
- Dựa vào thời gian cố định hoặc đồng hồ hệ thống.
- Dữ liệu thử bị dùng chung, không được cô lập.
- Phụ thuộc môi trường/network bên ngoài không ổn định.
- Thứ tự chạy test hoặc trạng thái còn lại từ lần chạy trước.
- Assertion quá nhạy với hiệu năng, animation hoặc khác biệt môi trường.

Không nên gọi mọi thất bại không tái hiện được ngay là “flaky”; có thể đó là lỗi đồng thời thực sự, cần điều tra.

### 9.2. Cách xử lý thay vì chỉ chạy lại đến khi xanh

1. Lưu **bằng chứng lỗi**: tình huống, seed, phiên bản, log an toàn và thời điểm.
2. Tái hiện với môi trường/dữ liệu được kiểm soát.
3. Phân loại: lỗi sản phẩm, lỗi test, vấn đề hạ tầng hay thiếu hợp đồng?
4. Sửa nguyên nhân: dùng điều kiện chờ theo trạng thái thay cho sleep cố định, cô lập dữ liệu, ổn định dependency.
5. Chạy lặp có mục đích để xác minh độ ổn định.
6. Nếu phải **quarantine**, ghi rõ người theo dõi, mức rủi ro, phạm vi và điều kiện khôi phục; không mặc định coi kiểm tra quan trọng đã qua.

**“Rerun đến khi xanh” không phải chính sách chất lượng.** Nó có thể che một race condition nghiêm trọng và làm báo cáo CI không đáng tin.

### 9.3. Dữ liệu và môi trường là một phần của chiến lược test

Test tốt cần có môi trường đáng tin:

| Vấn đề | Hậu quả | Cách cải thiện |
|---|---|---|
| Test dùng chung tài khoản và dữ liệu | Test ảnh hưởng nhau, kết quả phụ thuộc thứ tự | Tạo dữ liệu riêng và dọn đúng phạm vi |
| Phụ thuộc môi trường demo bị thay đổi thủ công | Lỗi không thể tái hiện | Quản lý cấu hình, version và môi trường |
| Sử dụng dữ liệu nhạy cảm thật | Rủi ro riêng tư và tuân thủ | Dùng dữ liệu tổng hợp/được xử lý đúng chính sách |
| Test đọc đồng hồ hoặc thời gian thực | Kết quả lệch theo múi giờ, ngày nghỉ | Inject clock/điều khiển thời gian ở cấp phù hợp |
| Hợp đồng API đối tác không ổn định | CI thường đỏ ngoài khả năng nhóm kiểm soát | Stub theo contract, kiểm tra tương thích thực ở nhịp phù hợp |
| E2E phụ thuộc selector CSS dễ đổi | Test vỡ dù hành vi đúng | Dùng locator ổn định, kiểm tra hành vi và tín hiệu người dùng |

Đừng cố làm mọi môi trường **giống hệt production** bằng cách sao chép dữ liệu thật; hãy lựa chọn mức đại diện theo rủi ro, chi phí và bảo mật.

### 9.4. Test doubles: dùng đúng chỗ

Một **fake repository** giúp unit test nhanh và tách biệt, nhưng fake có thể hành xử khác database thật. Một **mock** giúp kiểm tra tương tác quan trọng, nhưng nếu assert mọi lần gọi nội bộ thì refactor dễ làm vỡ test vô ích.

Hướng thực hành:

- Dùng test double để **cô lập logic** và tạo tình huống khó tái hiện.
- Dùng contract/integration test để bảo đảm **ranh giới với dependency thật** không bị giả định sai.
- Ưu tiên assert **kết quả có nghĩa**, chỉ kiểm tra chi tiết tương tác khi chúng là một phần hợp đồng cần bảo vệ.
- Không xem một bộ mock test xanh là bằng chứng toàn bộ hệ thống hoạt động.

### 9.5. Tốc độ phản hồi và WIP của bước kiểm thử

Nếu Developers mở nhiều PBI, tới cuối Sprint mới chuyển đồng loạt sang Test, hàng chờ tăng dù mỗi test riêng chạy nhanh.

Một số cải tiến có thể kết hợp:

- Chia PBI thành **lát dọc nhỏ** gồm code, tích hợp và kiểm tra đủ chất lượng.
- Đưa trao đổi acceptance criteria tới trước khi thực hiện.
- Dùng **WIP limit** để ngăn nhóm bắt đầu thêm quá nhiều việc.
- Ưu tiên xử lý PBI bị chặn ở review/test trước khi kéo việc mới.
- Tự động hóa kiểm tra lặp ổn định và giữ exploratory testing cho vấn đề cần tư duy.
- Làm rõ Definition of Done để không chuyển sớm một PBI chưa đạt chuẩn thành Done.

Kanban giúp **phơi bày điểm chờ**, còn chiến lược kiểm thử nhiều mức giúp **rút ngắn phản hồi ở từng khâu**.

## 10. Các phương pháp TDD, BDD, ATDD giúp đặt test vào đúng mục đích

### 10.1. TDD: dẫn dắt code bằng test nhỏ

**Test-Driven Development** thường đi theo **Red–Green–Refactor**:

1. Viết một test thất bại cho hành vi nhỏ.
2. Viết code tối thiểu làm test đạt.
3. Refactor và chạy lại test.

TDD thường dùng unit/component tests nhanh, nhưng không đồng nghĩa mọi test TDD đều phải là unit. Nó giúp thiết kế code và sửa đổi an toàn hơn, **không tự khám phá nhu cầu người dùng**.

### 10.2. ATDD: dẫn dắt bằng ví dụ chấp nhận

**Acceptance Test-Driven Development** đặt những ví dụ cho thấy PBI/feature được chấp nhận **trước khi hiện thực**. Product Owner hoặc đại diện nghiệp vụ, Developers và Tester cùng làm rõ:

- Trường hợp thành công.
- Trường hợp thất bại hoặc ngoại lệ quan trọng.
- Điều kiện biên, bảo mật và trạng thái chưa xác định.
- Ranh giới phạm vi hiện tại.

Acceptance test có thể ở API/component/integration hoặc UI tùy hành vi; **không đồng nghĩa luôn là browser test**.

### 10.3. BDD: làm rõ ý nghĩa trước khi viết scenario

**Behavior-Driven Development** hỗ trợ khám phá quy tắc qua hội thoại, diễn đạt ví dụ bằng ngôn ngữ chung và tự động hóa khi phù hợp. Một cách nhìn là **Discovery → Formulation → Automation**.

**Given–When–Then là cú pháp hữu ích, không phải toàn bộ BDD.** Một file Gherkin có thể chạy xanh nhưng vẫn mô tả sai hành vi nếu nhóm chưa thống nhất “đã lưu” nghĩa gì.

### 10.4. Kết hợp mà không nhân đôi test

Với một PBI:

1. BDD giúp phát hiện khi nghiệp vụ và kỹ thuật đang hiểu khác nhau.
2. ATDD biến ví dụ đã thống nhất thành điều kiện chấp nhận.
3. TDD giúp Developers hiện thực những quy tắc nhỏ.
4. Contract/integration/E2E kiểm chứng các ranh giới liên quan.
5. DoD bảo vệ chất lượng Increment, phản hồi người dùng xác nhận outcome.

Cùng một ví dụ nghiệp vụ có thể phục vụ **BDD và ATDD**. Không cần có hai bộ test giống nhau chỉ để thỏa các nhãn phương pháp.

## 11. Scrum, Kanban và XP góp gì cho chất lượng liên tục?

### 11.1. Scrum: chất lượng của Increment không được che giấu

Theo Scrum Guide:

- **Product Backlog** có commitment **Product Goal**.
- **Sprint Backlog** có commitment **Sprint Goal**.
- **Increment** có commitment **Definition of Done**.

**Developers** chịu trách nhiệm tuân thủ DoD khi tạo Increment. Nếu một PBI chưa đáp ứng DoD, nó không phải một Increment hoàn thành, không được phát hành hay trình bày tại Sprint Review như đã Done; công việc chưa xong quay lại Product Backlog để xem xét.

Các vòng phản hồi kiểm thử có thể nối với:

| Hoạt động Scrum | Cơ hội phát hiện và cải thiện chất lượng |
|---|---|
| Product Backlog refinement | Làm rõ rủi ro, ví dụ chấp nhận và chia nhỏ PBI |
| Sprint Planning | Đặt Sprint Goal, xem cách thực hiện và kiểm chứng phần có giá trị |
| Daily Scrum | Kiểm tra nguy cơ Sprint Goal, blocker và điều chỉnh Sprint Backlog |
| Sprint Review | Kiểm tra Increment thực sự đã Done, kết quả và nhu cầu stakeholder |
| Sprint Retrospective | Sửa nguyên nhân làm test chậm, lỗi phát hiện muộn và chất lượng không ổn định |

**Scrum không quy định một bộ công cụ kiểm thử bắt buộc.** TDD, BDD, ATDD, CI, test pyramid và WIP limit là những thực hành bổ trợ có thể chọn theo bối cảnh.

### 11.2. Kanban: phản hồi cần đi cùng dòng công việc

Kanban giúp nhóm định nghĩa **workflow**, kiểm soát WIP và sử dụng các phép đo:

- **WIP:** bao nhiêu hạng mục đã bắt đầu nhưng chưa Done?
- **Work item age:** công việc đang mở đã chờ bao lâu?
- **Cycle time:** hạng mục đã Done mất bao lâu từ bắt đầu đến hoàn thành?
- **Throughput:** hoàn thành bao nhiêu hạng mục trong một giai đoạn?

Nếu nhiều PBI già đi tại bước integration test, nguyên nhân có thể là môi trường chậm, dữ liệu thử không ổn định, dependency khó truy cập hoặc phạm vi PBI quá lớn. Đổi tên cột không giải quyết được vấn đề; cần nhìn nguyên nhân thực.

**Giảm WIP không bảo đảm throughput tăng**, nhưng có thể giúp tập trung hoàn tất việc đang mở và giảm hàng đợi khi có chính sách phù hợp.

### 11.3. XP: kỹ thuật làm vòng phản hồi ngắn và đáng tin

**Extreme Programming** đóng góp những thực hành như:

- **TDD và refactoring:** phản hồi nhỏ, giữ thiết kế dễ sửa.
- **Pair programming và collective ownership:** phát hiện hiểu nhầm, chia sẻ kiến thức, tránh phụ thuộc một người.
- **Continuous Integration:** nhận phản hồi tích hợp thường xuyên.
- **Small releases:** đưa lát cắt đủ chất lượng tới kiểm chứng sớm.
- **Customer collaboration:** giữ test hướng tới hành vi có giá trị.

Những thực hành **hỗ trợ nhau**: CI đáng tin giúp nhiều người cùng sửa code an toàn; thay đổi nhỏ giúp CI dễ chẩn đoán; test bảo vệ refactoring; phát hành nhỏ giúp kiểm chứng giả thuyết sản phẩm.

### 11.4. Lean: giảm chi phí lỗi lan qua nhiều khâu

Lean gợi ý **xây chất lượng tại nguồn**:

- Phát hiện sai khác càng gần nơi phát sinh càng hợp lý.
- Không đẩy việc lỗi sang bước sau chỉ để báo cột trước đã xong.
- Giảm lô công việc và công việc dở dang không cần thiết.
- Làm lỗi và blocker minh bạch để cải tiến nguyên nhân.

Phản hồi sớm không có nghĩa dừng mọi công việc bất cứ khi nào một test bất kỳ đỏ. Mức phản ứng phải tương xứng **rủi ro, hậu quả và chính sách chất lượng**.

## 12. Case study: thiết kế danh mục kiểm thử cho luồng lưu tiến độ

### 12.1. Bối cảnh sản phẩm

Một Scrum Team quản lý ứng dụng học trực tuyến. Người dùng mới có thể đăng ký, mở bài và lưu tiến độ để tiếp tục sau.

**Product Goal:** giúp người học bắt đầu và hoàn thành bài đầu thuận lợi mà không bị mất tiến độ trong điều kiện hỗ trợ.

**Sprint Goal minh họa:** “Người học mở bài đầu, lưu được tiến độ và nhận thông báo đúng khi lưu thành công hoặc thất bại.”

Hệ thống có:

- Giao diện web/mobile.
- API tiến độ.
- Database lưu trạng thái.
- Dịch vụ định danh/quyền truy cập.
- Hệ thống giám sát và phản hồi hỗ trợ.

Nhóm không thể chạy mọi kiểm tra đắt đỏ cho từng thay đổi, nhưng cũng không thể tin một vài unit tests là đủ.

### 12.2. Lập bảng rủi ro trước khi chọn tool

| Rủi ro | Mức tác động | Mức kiểm tra ưu tiên | Phản hồi cần có trước |
|---|---|---|---|
| Logic báo thành công khi lưu thất bại | Cao vì tạo kỳ vọng sai | Unit + component | Code merge |
| UI hiểu sai trạng thái API | Cao | Contract + component UI | Merge/integrate |
| Ghi database sai phiên bản tiến độ | Cao vì mất dữ liệu | Integration với database phù hợp | Release |
| Tài khoản khác đọc được tiến độ | Rất cao vì quyền riêng tư | Unit cho quy tắc + API/integration security | Merge/release theo chính sách |
| Luồng mở bài–lưu–mở lại bị đứt | Cao | E2E hành trình chính | Release |
| Trang lưu quá chậm ở lượng dùng lớn | Theo mục tiêu dịch vụ | Performance + production monitoring | Release/rollout theo mức rủi ro |
| Thông báo lỗi khó hiểu với người học | Vừa, ảnh hưởng trải nghiệm | Exploratory/UX/accessibility | Trước và sau phát hành |
| Người học vẫn bỏ dở vì bài quá khó | Ảnh hưởng outcome sản phẩm | Quan sát, phân tích hành vi, nghiên cứu | Sau khi có dữ liệu sử dụng |

Các mức tác động là **giả định minh họa**. Trên sản phẩm thật cần xem luật, hợp đồng, mức nhạy cảm dữ liệu và hậu quả thực tế.

### 12.3. Chia lát cắt và chọn kiểm tra vừa đủ

Lát cắt đầu:

> “Trong một thiết bị có kết nối, người học được xác nhận đã lưu khi backend phản hồi kết quả lưu hợp lệ; khi thất bại hoặc chưa xác định, UI không báo thành công giả.”

Điều ngoài phạm vi ban đầu: đồng bộ offline đầy đủ và xử lý mọi xung đột từ nhiều thiết bị. Không được xem các vấn đề này đã giải quyết nếu chưa có yêu cầu và bằng chứng.

Nhóm chọn:

1. **Unit/component:** trạng thái kết quả lưu và thông điệp UI.
2. **Contract:** ba trạng thái CONFIRMED, FAILED, UNKNOWN được hiểu nhất quán giữa UI/API.
3. **Integration:** API–database lưu và đọc lại trong môi trường thử, có tình huống thất bại.
4. **E2E:** một hành trình từ mở bài tới lưu/mở lại, thêm một kịch bản lỗi quan trọng.
5. **Bảo mật:** quyền truy cập dữ liệu theo chính sách.
6. **Exploratory:** thử ngắt mạng, chuyển tab và bấm lặp để tìm tình huống chưa dự đoán.
7. **Production:** theo dõi lỗi và phản hồi người dùng khi có rollout phù hợp.

### 12.4. Một vòng làm việc trong Sprint

**Trước khi code:** Product Owner, Developers và Tester làm rõ nghĩa “đã lưu”. Họ viết acceptance examples cho thành công, thất bại và trạng thái chưa biết. Chuyên gia bảo mật góp ý rủi ro đọc sai tiến độ.

**Khi code:** Developers dùng TDD cho ánh xạ trạng thái, code nhỏ và refactor. Component UI test xác nhận trạng thái FAILED không tạo thông báo thành công.

**Trong CI:** static checks, unit/component và contract tests chạy; integration test quan trọng bảo đảm API không lệch hợp đồng.

**Khi tích hợp:** nhóm tạo dữ liệu thử riêng, kiểm tra lưu/đọc lại và migration. Một lỗi transaction được phát hiện; nhóm sửa trước khi kéo nhiều PBI mới.

**Trước phát hành:** E2E hành trình chính, quyền truy cập và các kiểm tra vận hành theo DoD đạt. Phần offline chưa đáp ứng chính sách không được giới thiệu như đã hoàn thành.

**Sau phát hành có kiểm soát:** nhóm quan sát tỷ lệ lưu thất bại và báo cáo mất tiến độ; nếu có dấu hiệu tăng lỗi, họ ứng cứu theo chính sách và kiểm tra khả năng khôi phục.

### 12.5. Sự cố: kiểm thử tích hợp thất bại ngẫu nhiên

Giả sử integration test lưu tiến độ **đôi lúc đỏ** khi chạy song song. Nhóm không xóa test hoặc đánh dấu luôn xanh. Họ điều tra thấy hai test dùng chung tài khoản và cùng sửa một bản ghi.

Giải pháp:

- Tạo mỗi test một tài khoản/bản ghi riêng.
- Bảo đảm test cleanup đúng dữ liệu của chính nó.
- Chỉ phụ thuộc vào trạng thái đã xác nhận, không chờ ngủ cố định.
- Chạy lặp theo cách kiểm soát để xác nhận test ổn định.
- Bổ sung chính sách dữ liệu thử để tránh lỗi tương tự.

Nhờ vậy CI trở lại là **tín hiệu đáng tin**, thay vì chuỗi cảnh báo khiến mọi người bỏ qua.

### 12.6. Giả định dữ liệu sau cải tiến

Giả sử hai giai đoạn quan sát có số liệu **hoàn toàn minh họa**:

| Tín hiệu | Trước | Sau | Điều cần kiểm chứng thêm |
|---|---:|---:|---|
| CI phản hồi trung vị | 22 phút | 9 phút | Có bỏ kiểm tra quan trọng không? |
| PBI bị mở lại vì lỗi tích hợp muộn | 7 | 3 | Cách ghi lỗi và số lượng PBI có giống nhau? |
| Lỗi lưu tiến độ được báo sau phát hành | 16 | 5 | Lượng người dùng/thời gian quan sát tương đương? |
| Work item age của PBI đang chờ test | Có một số quá 10 ngày | Giảm còn một số ít | Có công việc bị chuyển sang cột ẩn không? |
| Người học hoàn thành bài đầu trong 7 ngày | 27% | 30% | Có thay đổi nội dung/chiến dịch/thiết bị cùng lúc? |

Những số liệu trên **không chứng minh** chính việc phân tầng test gây ra thay đổi outcome. Cần xem chất lượng dữ liệu, số mẫu, hệ thống đo, các yếu tố gây nhiễu và thời gian đủ dài.

### 12.7. Kết luận từ case study

- Unit tests giúp sửa logic nhanh nhưng **không thay thế** kiểm tra quyền truy cập hay database.
- Contract tests bảo vệ ý nghĩa giao tiếp, không tự bảo đảm giao diện thân thiện.
- Integration tests tìm vấn đề phụ thuộc thật; muốn đáng tin phải quản lý dữ liệu/môi trường.
- E2E chọn lọc bảo vệ một hành trình cốt lõi, không cần nhân bản mọi nhánh.
- Exploratory và production feedback tìm những điều **chưa có trong đặc tả**.
- DoD giữ nghĩa **Increment đã hoàn thành**, còn Product Goal cần bằng chứng người dùng.

## 13. Đo hiệu quả danh mục kiểm thử và vòng phản hồi

### 13.1. Không chọn một KPI duy nhất

| Nhóm chỉ số | Ví dụ | Câu hỏi giúp trả lời | Điều có thể gây hiểu sai |
|---|---|---|---|
| **Phản hồi CI** | Trung vị và phân bố thời gian đến kết quả | Developer biết sai sớm không? | Có thể “nhanh” vì bỏ test quan trọng |
| **Độ tin cậy test** | Tỷ lệ flaky, số lần retry, thời gian sửa build đỏ | Test có đáng tin để ra quyết định không? | Lỗi code thực có thể bị gắn nhầm flaky |
| **Phát hiện theo giai đoạn** | Lỗi phát hiện ở unit/integration/E2E/production | Rủi ro có đang bị phát hiện muộn? | Cách phân loại lỗi cần nhất quán |
| **Chất lượng sau phát hành** | Lỗi nghiêm trọng, sự cố, thời gian khôi phục | Người dùng đang chịu tác động gì? | Phụ thuộc lượng dùng và mức đo |
| **Chi phí bảo trì** | Test sửa khi UI đổi không liên quan behavior | Có test trùng hoặc bám chi tiết cài đặt không? | Mọi thay đổi test không phải lãng phí |
| **Dòng công việc** | WIP, work item age, cycle time, throughput | Kiểm thử có là điểm tắc của việc đạt Done không? | Không đo giá trị người dùng trực tiếp |
| **Outcome sản phẩm** | Người học tiếp tục và hoàn thành bài | Increment có giải quyết vấn đề không? | Cần xem phân khúc và thay đổi đồng thời |
| **Sức khỏe nhóm** | Áp lực review, làm lại, thời gian ngoài giờ | Quy trình phản hồi có bền vững không? | Số trung bình có thể che quá tải cục bộ |

### 13.2. Những con số cần định nghĩa rõ

**Thời gian phản hồi CI** có thể tính từ lúc push commit/pull request đến khi có **kết quả đủ tin cậy để Developer hành động**. Không trộn thời gian xếp hàng, thời gian chạy và thời gian chờ người review nếu mục tiêu đo khác nhau.

**Tỷ lệ test flaky** cần định nghĩa cách phát hiện: ví dụ số test có kết quả không ổn định trên tổng test được đánh giá trong một khoảng, có phân loại nguyên nhân. Không dùng mọi lần retry là bằng chứng chắc chắn test flaky.

**Defect escape** có thể theo dõi lỗi được xác minh sau phát hành, nhưng phải cân nhắc mức nghiêm trọng, số người dùng, khả năng phát hiện và thời gian quan sát. Không đếm mọi bug giống nhau.

**Coverage** giúp biết phần code đã được thực thi theo cách đo nhất định, **không cho biết test đã kiểm tra đúng quy tắc hoặc có ngăn lỗi quan trọng hay không**.

### 13.3. Chọn cải tiến bằng giả thuyết

~~~text
Quan sát:
  E2E suite mất nhiều thời gian, thường thất bại do dữ liệu dùng chung.
  Nhiều lỗi API đơn giản chỉ bị phát hiện khi chạy E2E cuối Sprint.

Giả thuyết:
  Nếu đưa kiểm tra hợp đồng API và logic nhỏ xuống unit/component,
  đồng thời cô lập dữ liệu E2E,
  nhóm sẽ nhận phản hồi nhanh và đáng tin hơn.

Thử nghiệm:
  Chọn các PBI lưu tiến độ và một số scenario lỗi thường gặp.
  Giữ E2E hành trình chính; thêm contract/unit tests gần nguồn.
  Cô lập dữ liệu, cải thiện điểm chờ khi kiểm thử.

Tín hiệu:
  Thời gian CI, tỷ lệ flaky, lỗi hợp đồng phát hiện trước merge,
  work item age và PBI đạt DoD.

Tín hiệu bảo vệ:
  Lỗi production, độ phủ rủi ro cao, tải vận hành, chi phí bảo trì.

Xem lại:
  Sau một số Sprint đủ dữ liệu và phản hồi người dùng.

Quyết định:
  Giữ, điều chỉnh hoặc dừng giải pháp theo bằng chứng.
~~~

Đây là **mẫu thử nghiệm cải tiến**, không phải quy định mọi đội phải tổ chức số Sprint giống nhau.

## 14. Các ngộ nhận phổ biến

| Ngộ nhận | Vì sao nguy hiểm? | Cách tiếp cận phù hợp |
|---|---|---|
| “Càng nhiều test càng tốt.” | Test trùng, chậm, không bảo vệ rủi ro thật | Chọn test dựa trên hành vi/rủi ro và giá trị phản hồi |
| “Chỉ unit test là đủ vì chạy nhanh.” | Bỏ sót tích hợp, cấu hình, giao diện và dữ liệu | Thêm contract/integration/E2E chọn lọc |
| “Chỉ E2E test là đủ vì giống người dùng.” | Phản hồi chậm, test giòn, chẩn đoán khó | Đưa kiểm tra quy tắc xuống tầng nhỏ khi có thể |
| “Contract test bảo đảm nghiệp vụ đúng.” | Hai service có thể tuân schema nhưng cùng hiểu sai quy tắc | Kết hợp ví dụ nghiệp vụ và test tích hợp/chấp nhận |
| “Mọi acceptance test phải chạy trong browser.” | Chi phí cao và dễ bị ảnh hưởng UI | Kiểm chứng ở tầng thấp nhất đủ bằng chứng |
| “TDD = unit testing.” | Nhầm cách phát triển với cấp kiểm thử | Phân biệt vòng test-first với ranh giới test |
| “BDD = Given–When–Then.” | Scenario có cú pháp nhưng không có hiểu biết chung | Ưu tiên Discovery và ví dụ nghiệp vụ |
| “Coverage cao chứng minh phần mềm an toàn.” | Có thể không test các trường hợp quan trọng | Dùng threat/risk-based testing và nhiều lớp kiểm soát |
| “CI đỏ cứ rerun tới xanh.” | Giấu flaky hoặc race condition thực | Điều tra nguyên nhân, ổn định test và môi trường |
| “Chuyển test chậm sang nightly là xong.” | Lỗi có thể lọt vào bản phát hành trước khi có kết quả | Xác định gate thiết yếu theo mức rủi ro |
| “Test cùng dữ liệu production giúp giống thật nhất.” | Rủi ro dữ liệu riêng tư và thay đổi không kiểm soát | Dùng dữ liệu thử, tổng hợp hoặc xử lý theo chính sách |
| “Build xanh thì PBI Done.” | Chưa chắc đạt acceptance criteria, DoD hoặc tích hợp | Kiểm tra chuẩn hoàn thành đầy đủ |
| “Kiểm thử là việc của QA cuối Sprint.” | Lỗi và hiểu nhầm dồn sang giai đoạn muộn | Chất lượng là trách nhiệm chung từ refinement tới vận hành |
| “Bật feature flag nghĩa là không cần test.” | Có thể làm cả trạng thái bật/tắt gây lỗi | Kiểm tra những trạng thái và chuyển đổi có rủi ro |
| “Giảm thời gian CI bằng mọi giá.” | Phản hồi có thể nhanh nhưng sai hoặc thiếu | Cân bằng nhanh, đúng, ổn định và khả năng chẩn đoán |
| “Test xanh nghĩa là Product Goal đạt.” | Output chất lượng chưa chắc tạo outcome | Quan sát hành vi người dùng và phản hồi sản phẩm |

## 15. Checklist tổ chức kiểm thử nhiều mức

### Trước khi triển khai một PBI

1. **Product Goal:** PBI góp giá trị hoặc giảm rủi ro quan trọng nào?
2. **Nghiệp vụ:** tình huống thành công, thất bại, trạng thái chưa xác định nào cần làm rõ?
3. **Ranh giới:** code, API, database, UI và dependency nào tham gia?
4. **Rủi ro:** có ảnh hưởng dữ liệu, bảo mật, thanh toán, hiệu năng, truy cập hoặc khả năng tiếp cận không?
5. **Acceptance:** điều kiện chấp nhận có thể kiểm chứng và được hiểu chung chưa?
6. **Phạm vi:** có thể giao lát cắt dọc nhỏ, tích hợp và học sớm không?

### Trong khi phát triển

7. **Unit/component:** quy tắc nhỏ có thể được bảo vệ bằng test nhanh không?
8. **Contract:** các bên có cùng hiểu định dạng và ý nghĩa trạng thái không?
9. **Integration:** dependency thật nào nhất thiết phải được kiểm chứng?
10. **E2E:** hành trình nào cần bảo vệ từ góc nhìn người dùng?
11. **Exploratory:** có tình huống nào tự động hóa chưa đủ để phát hiện?
12. **CI:** kết quả có đến đủ sớm, rõ nguyên nhân và đáng tin không?
13. **Dữ liệu thử:** có cô lập và bảo vệ dữ liệu nhạy cảm không?
14. **Flaky:** test thất bại bất thường có được điều tra thay vì bỏ qua không?
15. **WIP:** công việc chờ review/test có được làm hiển thị để hỗ trợ hoàn tất không?

### Trước và sau phát hành

16. **DoD:** Increment có thực sự tích hợp và đạt tiêu chuẩn bắt buộc không?
17. **Gate:** kiểm tra thiết yếu theo rủi ro có được hoàn tất trước quyết định phát hành không?
18. **Rollout:** có cách phát hiện và xử lý lỗi sau triển khai phù hợp không?
19. **Production:** telemetry đủ để theo dõi lỗi nhưng không lộ dữ liệu trái phép không?
20. **Outcome:** kết quả người dùng cần quan sát là gì, mẫu số và thời gian thế nào?
21. **Thích ứng:** test, Product Backlog hoặc workflow có được điều chỉnh theo thông tin mới không?

Checklist là **công cụ hỗ trợ quyết định**, không phải yêu cầu ký duyệt hàng chục biểu mẫu cho mọi sửa đổi nhỏ.

## 16. Bài tập thực hành

### Bài tập 1 — Chọn mức kiểm thử phù hợp

Hãy đề xuất **mức kiểm tra sớm nhất đủ hữu ích** và một kiểm tra bổ trợ cho từng rủi ro:

1. Hàm tính giảm giá có thể trả kết quả âm trái với nghiệp vụ.
2. API đổi tên trường nhưng UI vẫn đọc tên cũ.
3. Migration database làm mất dữ liệu lịch sử khi nâng cấp.
4. Luồng thanh toán chạy đúng trong service nhưng UI báo hoàn tất sớm.
5. Người dùng khác đọc được tiến độ học không thuộc quyền.
6. Trang bài học rất chậm khi có nhiều người truy cập.

**Gợi ý:** không cần E2E cho mọi phép tính; cũng không được dùng unit tests để tuyên bố dữ liệu migration thật đã an toàn.

### Bài tập 2 — Thiết kế danh mục kiểm thử cho user story

User story: “Là người học đang học dở, tôi muốn lưu và mở lại tiến độ để không phải học lại.”

Lập bảng:

| Rủi ro | Acceptance example | Unit/component | Contract/integration | E2E/khám phá | Phản hồi sau phát hành |
|---|---|---|---|---|---|
| Thành công | ? | ? | ? | ? | ? |
| Dịch vụ lưu thất bại | ? | ? | ? | ? | ? |
| Timeout chưa biết kết quả | ? | ? | ? | ? | ? |
| Không được đọc dữ liệu người khác | ? | ? | ? | ? | ? |

**Gợi ý:** một ô có thể để “không cần” nếu đã nêu lý do rõ, nhưng những rủi ro cao phải có bằng chứng phù hợp và DoD được bảo vệ.

### Bài tập 3 — Đánh giá một pipeline chậm

Một đội có 600 unit tests chạy nhanh, 80 integration tests dùng chung database và 250 browser E2E tests. Pull request thường chờ rất lâu, trong khi một phần lớn browser tests lỗi ngẫu nhiên.

**Yêu cầu:**

1. Nêu ba nguyên nhân có thể khiến vòng phản hồi kém.
2. Chọn hai hành vi đang được kiểm tra bằng E2E có thể chuyển xuống unit/component/contract.
3. Chỉ ra những E2E nào vẫn nên giữ vì rủi ro hành trình.
4. Đề xuất cách cô lập dữ liệu và xử lý flaky tests.
5. Nêu ba tín hiệu cần đo trước–sau để biết cải tiến có ích.

**Gợi ý:** đừng xóa hàng loạt E2E chỉ để CI nhanh nếu chưa biết chúng bảo vệ rủi ro nào.

### Bài tập 4 — Phân biệt ba trạng thái lưu

Product Owner yêu cầu: “Phải báo thành công ngay khi bấm lưu.” Developers biết backend có thể timeout.

**Yêu cầu:**

1. Viết ba câu hỏi BDD Discovery để làm rõ ý nghĩa.
2. Viết acceptance examples ATDD cho **CONFIRMED, FAILED và UNKNOWN**.
3. Chọn hai hoặc ba TDD unit tests cho logic ánh xạ.
4. Nêu một contract test và một integration test cần có.
5. Giải thích vì sao timeout **không được tùy tiện coi** là chắc chắn thất bại hoặc thành công.

**Gợi ý:** hành vi phải dựa trên bằng chứng kết quả và chính sách đối soát, không chỉ trên sự kiện đã gửi request.

### Bài tập 5 — Khi nào test xanh chưa đủ để Done?

Trong Sprint, một PBI đã qua unit, component và acceptance tests; nhưng test quyền truy cập bắt buộc thất bại, môi trường tích hợp chưa nhận thay đổi và chưa có cơ chế theo dõi lỗi thiết yếu.

**Yêu cầu:** giải thích phần nào chưa đạt Definition of Done, nhóm cần minh bạch gì trong Sprint Backlog, thương lượng với Product Owner ra sao và điều gì có thể trình bày tại Sprint Review như Increment đã hoàn thành.

**Gợi ý:** không được hợp thức hóa công việc chưa đạt DoD chỉ vì số test nghiệp vụ xanh hoặc đã xong code.

### Bài tập 6 — Xử lý flaky integration test

Một bài integration test kiểm tra lưu tiến độ lúc chạy riêng thì qua, chạy song song thì đỏ. Hai test cùng sửa tài khoản dùng chung.

**Yêu cầu:**

1. Phân loại nguyên nhân nghi vấn và bằng chứng cần thu.
2. Đề xuất phương án tạo dữ liệu riêng, cleanup và kiểm soát đồng thời.
3. Nêu khi nào nên quarantine test và điều kiện khôi phục.
4. Giải thích vì sao rerun liên tục không phải giải pháp lâu dài.
5. Xác định cách đo độ ổn định sau thay đổi.

### Bài tập 7 — Tổ chức kiểm thử theo rủi ro phát hành

Một đội triển khai hai thay đổi trong cùng tuần: sửa màu sắc của nút mở bài và thay quy tắc quyền truy cập của API tiến độ.

**Yêu cầu:** đề xuất khác biệt về unit, contract/integration, E2E, security checks và quan sát sau phát hành. Chỉ ra chính sách nào cần chạy trước merge hoặc release, loại nào có thể chạy định kỳ khi rủi ro cho phép.

**Gợi ý:** không nên dùng cùng bộ kiểm tra cho mọi mức rủi ro, nhưng luôn phải tuân thủ chuẩn DoD và các kiểm soát bắt buộc.

### Bài tập 8 — Thiết kế thử nghiệm cải tiến vòng phản hồi

Trong ba Sprint, nhóm phát hiện lỗi tích hợp quá muộn và có nhiều PBI bị chặn ở bước kiểm thử. Hãy viết một thử nghiệm cải tiến:

~~~text
Product Goal / Sprint Goal liên quan:
Vấn đề và bằng chứng nền:
Những rủi ro cần nhận phản hồi sớm:
Các test cần đưa xuống unit/component/contract:
Những integration/E2E tests vẫn giữ:
Chính sách CI/pull request:
Chính sách dữ liệu thử và xử lý flaky:
Kiểm soát WIP và blocker ở bước Test:
Các tín hiệu cycle time, work item age, lỗi, CI:
Tín hiệu bảo vệ chất lượng và nhịp bền vững:
Điểm xem lại và cách quyết định giữ/sửa/dừng:
~~~

**Tự đánh giá:** nhóm có biết **mỗi loại test bảo vệ rủi ro gì, chạy khi nào, ai phản ứng khi đỏ và liệu phản hồi ấy có đến đủ sớm** hay không?

## 17. Tổng kết

Chất lượng liên tục không phải một cuộc đua xem ai có nhiều test nhất. Đó là cách tổ chức **những phản hồi bổ sung nhau** để giảm thời gian từ lúc sai lệch xuất hiện đến lúc nhóm nhận biết, sửa và kiểm chứng lại.

Những điều quan trọng:

1. **Chọn cấp kiểm thử theo ranh giới rủi ro:** unit/component cho quy tắc nhỏ; contract cho thỏa thuận API; integration cho các phần thật; E2E chọn lọc cho hành trình người dùng.
2. **Không bỏ qua những lớp khác:** static checks, bảo mật, hiệu năng, resilience, accessibility, exploratory testing và quan sát thực phục vụ những rủi ro mà happy-path functional tests không chứng minh được.
3. **Thiết kế vòng phản hồi phù hợp:** test nhanh ở gần lúc code, kiểm tra ranh giới trước khi thay đổi nguy hiểm lan rộng, kiểm tra sâu theo rủi ro trước phát hành và tiếp tục học từ production.
4. **Phản hồi phải đáng tin:** cô lập dữ liệu, giảm flaky, xử lý build đỏ, dùng test doubles đúng chỗ và kiểm chứng dependency thật khi cần.
5. **TDD, BDD, ATDD là cách học và phát triển**, không phải tên khác của unit/E2E tests; có thể kết hợp mà không nhân đôi các ví dụ chấp nhận.
6. **Giữ Definition of Done:** CI xanh chưa đủ nếu Increment chưa tích hợp và chưa đáp ứng chất lượng bắt buộc.
7. **Scrum, Kanban, XP bổ trợ:** Scrum giữ mục tiêu và chuẩn hoàn thành, Kanban phơi bày dòng công việc và điểm tắc, XP tăng cường phản hồi kỹ thuật thường xuyên.
8. **Đo kết quả thật:** thời gian phản hồi, test flaky, lỗi sau phát hành, dòng công việc và outcome người dùng cần được nhìn cùng nhau.

> **Câu hỏi ghi nhớ:** “Với lỗi quan trọng tiếp theo, **mức kiểm thử nào có thể báo sớm nhất mà vẫn đủ tin cậy**, và nhóm sẽ hành động thế nào ngay khi nhận tín hiệu đó?”

### Tài liệu tham khảo

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Increment, Definition of Done, trách nhiệm Developers và các vòng kiểm tra–thích ứng.
- [Agile Alliance — Test-Driven Development](https://agilealliance.org/glossary/tdd/) — vai trò của TDD và phản hồi phát triển dựa trên test.
- [Cucumber — Behavior-Driven Development](https://cucumber.io/docs/bdd/) — khám phá hành vi, đặc tả ví dụ và cộng tác.
- [Martin Fowler — Test Pyramid](https://martinfowler.com/bliki/TestPyramid.html) — cách suy nghĩ về mức kiểm tra, phản hồi và chi phí test.
- [Martin Fowler — Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html) — tích hợp thường xuyên, phản hồi nhanh và xử lý lỗi tích hợp.
- [Google Testing Blog](https://testing.googleblog.com/) — các thảo luận kỹ thuật về chiến lược kiểm thử, độ tin cậy và tự động hóa.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, throughput, work item age và cycle time.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — giao phần mềm có giá trị thường xuyên, sự xuất sắc kỹ thuật và cải tiến liên tục.

# Biểu mẫu nhiều bước và thời hạn tồn tại dữ liệu

## 1. Khi nào cần biểu mẫu nhiều bước?

Biểu mẫu nhiều bước (multi-step form hoặc wizard) chia một quy trình nhập liệu dài thành các màn hình nhỏ theo thứ tự. Người dùng hoàn thành một phần, chuyển sang bước tiếp theo, có thể quay lại chỉnh sửa, rồi xác nhận để gửi toàn bộ dữ liệu.

Ví dụ, quy trình đăng ký dịch vụ có thể gồm:

1. Nhập thông tin cá nhân.
2. Chọn gói dịch vụ và tùy chọn.
3. Xem lại thông tin và xác nhận.

Trong MVC web, mỗi bước thường tương ứng với một request GET để hiển thị và một request POST để tiếp nhận dữ liệu. Vì HTTP không giữ trạng thái nghiệp vụ giữa các request, ứng dụng cần quyết định dữ liệu đã nhập sẽ tồn tại ở đâu, trong bao lâu và ai được phép tiếp tục quy trình.

Đây là hai vấn đề gắn chặt với nhau: thiết kế luồng bước và quản lý vòng đời dữ liệu. Nếu chỉ chuyển từ trang này sang trang khác mà không có cách lưu trạng thái phù hợp, dữ liệu sẽ mất khi request kết thúc hoặc khi người dùng quay lại sau một khoảng thời gian.

## 2. Luồng tổng thể của một wizard

Một quy trình đăng ký ba bước có thể diễn ra như sau:

~~~mermaid
flowchart TD
    A[GET /registrations/new] --> B[Hiển thị bước 1]
    B --> C[POST dữ liệu bước 1]
    C --> D{Binding và validation}
    D -->|Không hợp lệ| B
    D -->|Hợp lệ| E[Lưu trạng thái bước 1]
    E --> F[Redirect đến bước 2]
    F --> G[GET /registrations/step-2]
    G --> H[Hiển thị bước 2]
    H --> I[POST dữ liệu bước 2]
    I --> J{Validation và quy tắc nghiệp vụ}
    J -->|Không hợp lệ| H
    J -->|Hợp lệ| K[Lưu bản nháp]
    K --> L[GET trang xác nhận]
    L --> M[Người dùng xác nhận]
    M --> N[POST hoàn tất]
    N --> O[Kiểm tra cuối và ghi nhận nghiệp vụ]
    O --> P[Xóa trạng thái wizard]
    P --> Q[Redirect trang hoàn tất]
~~~

Luồng thực tế có thể có nhiều bước hơn, cho phép quay lại, bỏ qua một bước tùy điều kiện hoặc dừng để tiếp tục sau. Dù phức tạp đến đâu, server cần xác định rõ bước hiện tại, bước nào được phép tiếp theo và dữ liệu nào đã được xác nhận.

## 3. Mô hình hóa quy trình như một state machine

Không nên xem wizard chỉ là một tập URL. Nó là một quy trình có trạng thái và các chuyển đổi được phép. Ví dụ:

| Trạng thái | Chuyển đổi hợp lệ | Điều kiện |
|---|---|---|
| `STEP_1` | `STEP_2` | Thông tin cá nhân hợp lệ |
| `STEP_2` | `REVIEW` | Lựa chọn gói hợp lệ |
| `REVIEW` | `COMPLETED` | Người dùng xác nhận và kiểm tra cuối thành công |
| Bất kỳ bước đang mở | `EXPIRED` | Quá thời hạn quy trình |
| Bất kỳ bước đang mở | `CANCELLED` | Người dùng hủy quy trình |

State machine giúp server từ chối request đi sai thứ tự. Ví dụ, người dùng không thể gửi trực tiếp POST bước 3 khi chưa hoàn thành bước 1 và bước 2. Việc ẩn liên kết bước 3 trong giao diện không phải biện pháp bảo vệ; server phải kiểm tra trạng thái mỗi lần nhận request.

Trạng thái nên được biểu diễn bằng enum hoặc mã rõ ràng, chẳng hạn `currentStep` hoặc `status`. Nếu quy trình có nhánh, điều kiện chuyển trạng thái cần nằm trong Service hoặc một thành phần điều phối quy trình, thay vì rải rác trong nhiều template.

~~~java
public enum RegistrationStep {
    STEP_1,
    STEP_2,
    REVIEW,
    COMPLETED,
    EXPIRED,
    CANCELLED
}
~~~

Trạng thái do server quản lý. Không cho client tự gửi `currentStep=COMPLETED` hoặc `status=APPROVED` để quyết định quyền đi tiếp.

## 4. Dữ liệu tồn tại ở đâu và trong bao lâu?

Không có một nơi lưu trạng thái phù hợp cho mọi wizard. Hãy chọn theo thời gian người dùng cần hoàn thành, khả năng tiếp tục trên thiết bị khác, mức độ nhạy cảm và yêu cầu vận hành.

| Nơi lưu | Thời hạn thường dùng | Phù hợp với | Hạn chế chính |
|---|---|---|---|
| Request model | Chỉ trong một request | Dữ liệu dùng để render một trang | Mất sau khi response kết thúc |
| Flash attributes | Request kế tiếp sau redirect | Thông báo thành công hoặc lỗi ngắn hạn | Không phù hợp lưu toàn bộ tiến trình |
| HTTP session | Trong thời gian session còn hiệu lực | Wizard ngắn, một phiên làm việc | Khó tiếp tục trên thiết bị khác; có thể xung đột nhiều tab |
| Database draft | Theo thời hạn nghiệp vụ đã định | Quy trình dài, cần tiếp tục sau đăng xuất hoặc trên thiết bị khác | Cần quản lý quyền truy cập, hết hạn và dọn dữ liệu |
| Client storage | Theo chính sách trình duyệt hoặc ứng dụng | Tùy chọn giao diện không nhạy cảm | Người dùng kiểm soát được dữ liệu; không đáng tin để bảo vệ nghiệp vụ |

Request model không thể giữ dữ liệu giữa hai request. Flash attribute phù hợp để đưa thông báo qua redirect, không phải một kho lưu trữ wizard. Session và database draft là hai lựa chọn phổ biến cho dữ liệu nhiều bước.

Không lưu mật khẩu, thông tin thẻ thanh toán hoặc dữ liệu nhạy cảm không cần thiết trong session hay bản nháp kéo dài. Hãy giảm thiểu dữ liệu được giữ, đặt thời hạn rõ ràng và áp dụng biện pháp bảo vệ tương ứng.

## 5. Lưu wizard ngắn hạn trong HTTP session

Với một quy trình ngắn, người dùng thường hoàn thành trong một phiên và không cần tiếp tục trên thiết bị khác, có thể lưu đối tượng form trong session. Spring MVC hỗ trợ `@SessionAttributes` để giữ một model attribute qua các request của cùng Controller.

Ví dụ dưới đây minh họa wizard đăng ký hai bước. Các trường dữ liệu của biểu mẫu được binding vào `RegistrationWizardForm`; `currentStep` do server thay đổi và không nằm trong danh sách trường được phép binding.

~~~java
public interface StepOne {}
public interface StepTwo {}

public class RegistrationWizardForm {
    @NotBlank(groups = StepOne.class)
    private String fullName;

    @Email(groups = StepOne.class)
    @NotBlank(groups = StepOne.class)
    private String email;

    @NotBlank(groups = StepTwo.class)
    private String plan;

    private int currentStep = 1;

    public String getFullName() { return fullName; }
    public void setFullName(String value) { fullName = value; }
    public String getEmail() { return email; }
    public void setEmail(String value) { email = value; }
    public String getPlan() { return plan; }
    public void setPlan(String value) { plan = value; }
    public int getCurrentStep() { return currentStep; }
    public void setCurrentStep(int value) { currentStep = value; }

    public RegistrationCommand toCommand() {
        return new RegistrationCommand(fullName, email, plan);
    }
}
~~~

Ví dụ dùng validation groups để kiểm tra các trường tương ứng với từng bước. `RegistrationCommand` là dữ liệu đầu vào của use case, được định nghĩa riêng trong tầng ứng dụng. Trong dự án thực tế, có thể dùng các Form DTO riêng cho từng bước nếu cấu trúc dữ liệu hoặc quy tắc khác nhau nhiều.

### Controller quản lý session state

~~~java
@Controller
@RequestMapping("/registrations")
@SessionAttributes("wizard")
public class RegistrationWizardController {
    private final RegistrationService registrationService;

    public RegistrationWizardController(
            RegistrationService registrationService) {
        this.registrationService = registrationService;
    }

    @ModelAttribute("wizard")
    public RegistrationWizardForm newWizard() {
        return new RegistrationWizardForm();
    }

    @InitBinder("wizard")
    public void configureWizardBinder(WebDataBinder binder) {
        binder.setAllowedFields("fullName", "email", "plan");
    }

    @GetMapping("/new")
    public String start(Model model) {
        model.addAttribute("wizard", new RegistrationWizardForm());
        return "registrations/step-one";
    }

    @PostMapping("/step-one")
    public String submitStepOne(
            @Validated(StepOne.class)
            @ModelAttribute("wizard") RegistrationWizardForm form,
            BindingResult errors) {
        if (errors.hasErrors()) {
            return "registrations/step-one";
        }

        form.setCurrentStep(2);
        return "redirect:/registrations/step-two";
    }

    @GetMapping("/step-two")
    public String showStepTwo(
            @ModelAttribute("wizard") RegistrationWizardForm form) {
        if (form.getCurrentStep() != 2) {
            return "redirect:/registrations/new";
        }
        return "registrations/step-two";
    }

    @PostMapping("/step-two")
    public String finish(
            @Validated(StepTwo.class)
            @ModelAttribute("wizard") RegistrationWizardForm form,
            BindingResult errors,
            SessionStatus sessionStatus) {
        if (form.getCurrentStep() != 2) {
            return "redirect:/registrations/new";
        }
        if (errors.hasErrors()) {
            return "registrations/step-two";
        }

        registrationService.register(form.toCommand());
        sessionStatus.setComplete();
        return "redirect:/registrations/complete";
    }
}
~~~

Đây là ví dụ khái niệm; các import Spring, Bean Validation, `Model`, `WebDataBinder`, `BindingResult`, `SessionStatus` và các kiểu nghiệp vụ cần được khai báo trong dự án. `@SessionAttributes("wizard")` giữ thuộc tính `wizard` giữa các request của Controller. `@InitBinder` giới hạn các trường client được phép cập nhật; `currentStep` không được binding từ request.

`SessionStatus.setComplete()` đánh dấu kết thúc luồng session attributes do Controller quản lý. Gọi sau khi use case hoàn tất hoặc khi người dùng hủy quy trình. Không nhầm thao tác này với việc hủy toàn bộ HTTP session của người dùng.

Với lỗi validation, Controller trả lại đúng template của bước hiện tại để `BindingResult` và giá trị đã nhập vẫn còn trong request. Với thành công, redirect tạo request mới và session tiếp tục giữ dữ liệu cho bước tiếp theo.

### Giới hạn của session wizard

`@SessionAttributes` phù hợp với một luồng đơn giản, nhưng một thuộc tính session duy nhất có thể gây xung đột nếu người dùng mở nhiều wizard cùng lúc trong nhiều tab. Bắt đầu một quy trình mới có thể thay thế dữ liệu của quy trình cũ. Nếu cần nhiều luồng song song, hãy dùng một `flowId` riêng cho từng wizard và lưu trạng thái theo khóa đó trong session hoặc database.

Session cũng có thể hết hạn khi người dùng đang điền form. Khi request tiếp theo không còn trạng thái wizard, ứng dụng cần phát hiện luồng chưa được khởi tạo hoặc đã hết hạn và đưa người dùng về điểm bắt đầu với thông báo rõ ràng.

## 6. Lưu bản nháp trong database

Khi quy trình kéo dài nhiều giờ hoặc nhiều ngày, người dùng cần đăng xuất rồi tiếp tục, hoặc có thể dùng nhiều thiết bị, database draft thường phù hợp hơn session.

Một bản nháp có thể có cấu trúc như sau:

~~~text
RegistrationDraft
  id
  ownerUserId
  status
  currentStep
  fullName
  email
  selectedPlan
  createdAt
  updatedAt
  expiresAt
  version
~~~

`ownerUserId` xác định người sở hữu; `status` và `currentStep` do server quản lý; `expiresAt` xác định thời điểm hết hạn; `version` hỗ trợ phát hiện cập nhật đồng thời. Không cần lưu mọi trường trong một JSON không cấu trúc nếu có thể mô hình hóa rõ các dữ liệu quan trọng và cần truy vấn.

### Luồng sử dụng draft

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant C as Controller
    participant S as RegistrationService
    participant R as DraftRepository
    participant DB as Database
    B->>C: POST /registrations/{draftId}/step-1
    C->>S: saveStepOne(userId, draftId, form)
    S->>R: Tải draft theo ID
    R->>DB: SELECT draft
    DB-->>R: Draft và version
    R-->>S: Draft
    S->>S: Kiểm tra owner, trạng thái, thời hạn
    S->>S: Kiểm tra dữ liệu bước 1
    S->>R: Cập nhật draft và version
    R->>DB: UPDATE draft
    DB-->>R: Đã lưu
    R-->>S: Draft mới
    S-->>C: Kết quả bước 1
    C-->>B: Redirect đến bước 2
~~~

Mỗi lần gửi bước, Service tải bản nháp, xác minh người dùng sở hữu, kiểm tra trạng thái và thời hạn, validate dữ liệu rồi lưu cập nhật trong một transaction ngắn. Không giữ một transaction cơ sở dữ liệu mở trong toàn bộ thời gian người dùng điền form; thời gian chờ có thể kéo dài và chiếm connection hoặc lock không cần thiết.

### Ví dụ hợp đồng Service

~~~java
public interface RegistrationDraftService {
    DraftView start(UserId owner);

    DraftView saveStepOne(
            UserId owner, DraftId draftId, StepOneForm form);

    DraftView saveStepTwo(
            UserId owner, DraftId draftId, StepTwoForm form);

    RegistrationResult complete(UserId owner, DraftId draftId);

    void cancel(UserId owner, DraftId draftId);
}
~~~

Service nhận `owner` từ security context đã xác thực, không nhận giá trị chủ sở hữu do client tự khai báo. Repository nên truy vấn theo cả `draftId` và `ownerUserId` hoặc Service kiểm tra ownership trước mọi thao tác. Một ID khó đoán không thay thế kiểm tra quyền.

Ở bước cuối, Service tải draft, xác minh trạng thái đã hoàn tất các bước, chạy lại các quy tắc nghiệp vụ quan trọng và tạo đối tượng miền chính thức trong một transaction. Chỉ sau khi ghi thành công mới chuyển draft sang `COMPLETED` hoặc xóa dữ liệu tạm theo chính sách lưu trữ.

## 7. Chọn session hay database draft?

| Tiêu chí | Session | Database draft |
|---|---|---|
| Thời gian quy trình | Ngắn, trong một phiên | Dài, có thể qua nhiều phiên |
| Tiếp tục sau đăng xuất | Thường không | Có thể, sau khi xác thực lại |
| Dùng nhiều thiết bị | Không thuận tiện | Có thể |
| Nhiều wizard song song | Cần khóa/flow ID và quản lý riêng | Tự nhiên hơn với mỗi draft có ID |
| Dung lượng dữ liệu | Nên nhỏ | Có thể quản lý lượng dữ liệu lớn hơn theo chính sách |
| Vận hành nhiều máy chủ | Cần sticky session hoặc session store dùng chung | Lưu trữ tập trung, có transaction |
| Hết hạn | Theo timeout của session hoặc thời hạn riêng | Theo `expiresAt` và cơ chế dọn dữ liệu |
| Khả năng audit | Hạn chế nếu không ghi log riêng | Có thể lưu lịch sử thay đổi có chủ đích |

Chọn session cho wizard ngắn và ít dữ liệu. Chọn database draft khi người dùng cần lưu tiến trình, tiếp tục sau thời gian dài hoặc có nhiều luồng đồng thời. Có thể kết hợp: session giữ ID phiên hoặc flow ID, còn dữ liệu bản nháp nằm trong database.

Không nên lưu toàn bộ wizard trong cookie. Cookie được gửi theo request, có giới hạn kích thước, có thể bị sửa nếu không được bảo vệ và dễ làm lộ dữ liệu. Cookie phù hợp hơn với session identifier hoặc một mã tham chiếu ngắn được bảo vệ.

## 8. Thời hạn tồn tại và xử lý hết hạn

Mỗi wizard cần một chính sách thời hạn được xác định từ yêu cầu nghiệp vụ. Ví dụ, một đăng ký dịch vụ có thể hết hạn sau 24 giờ không hoạt động; một hồ sơ thanh toán có thể có thời hạn ngắn hơn. Không nên chọn thời hạn chỉ theo mặc định kỹ thuật mà không xem xét dữ liệu và rủi ro.

Cần phân biệt:

- **Session timeout:** thời gian session không hoạt động trước khi server hết hiệu lực session.
- **Draft expiration:** thời điểm bản nháp không còn được phép tiếp tục theo nghiệp vụ.
- **Retention period:** thời gian dữ liệu được giữ lại sau khi hoàn tất hoặc hủy vì lý do audit, hỗ trợ hoặc pháp lý.

Ba thời hạn này có thể khác nhau. Một session còn hiệu lực không có nghĩa draft vẫn hợp lệ; draft chưa hết hạn cũng không có nghĩa người dùng còn đăng nhập.

### Kiểm tra thời hạn ở server

Trước khi đọc hoặc cập nhật draft, Service cần so sánh thời gian hiện tại với `expiresAt` và trạng thái. Nếu đã hết hạn, không cho phép tiếp tục bước tiếp theo. Với HTML, có thể hiển thị trang “Quy trình đã hết hạn” và hướng dẫn bắt đầu lại; với API, có thể dùng status phù hợp như `410 Gone` nếu tài nguyên tạm đã hết hiệu lực theo hợp đồng.

Không dựa vào đồng hồ hoặc JavaScript ở trình duyệt để quyết định draft còn hạn. Client có thể thay đổi thời gian hoặc bỏ qua kiểm tra; server là nơi có thẩm quyền.

### Dọn bản nháp hết hạn

Database draft cần cơ chế dọn dữ liệu hết hạn, chẳng hạn một scheduled job tìm các bản nháp đã quá `expiresAt` và xóa hoặc chuyển sang trạng thái `EXPIRED`. Có thể dùng xóa mềm trước rồi xóa vật lý sau nếu cần audit. Cần có index trên `expiresAt` và phân lô việc dọn để tránh một transaction lớn.

Việc dọn dữ liệu cần tôn trọng retention policy. Không giữ dữ liệu cá nhân vô thời hạn chỉ vì nó từng là một bản nháp. Nếu cần giữ bản ghi audit sau khi xóa nội dung form, chỉ lưu những trường thực sự cần thiết.

## 9. Quay lại bước trước và xác nhận dữ liệu

Wizard thường cho phép người dùng quay lại chỉnh sửa. Khi đó cần quyết định dữ liệu bước sau có còn hợp lệ không.

Ví dụ, người dùng chọn gói dịch vụ ở bước 2, sau đó quay lại bước 1 và thay đổi quốc gia cư trú. Nếu danh sách gói phụ thuộc quốc gia, lựa chọn cũ có thể không còn hợp lệ. Khi dữ liệu đầu vào của bước trước thay đổi, Service cần đánh giá và xóa hoặc yêu cầu chọn lại các trường phụ thuộc.

Không nên chỉ đổi URL hoặc số bước mà giữ nguyên mọi giá trị. Quy tắc phụ thuộc giữa các bước cần được mô hình hóa rõ.

Trang review nên hiển thị toàn bộ dữ liệu sẽ được gửi và cho phép quay lại bước tương ứng. Khi người dùng nhấn xác nhận, server tải lại draft mới nhất, kiểm tra version, trạng thái, quyền sở hữu, thời hạn và toàn bộ quy tắc nghiệp vụ trước khi hoàn tất.

Validation theo từng bước giúp phản hồi sớm. Tuy nhiên, bước cuối vẫn phải kiểm tra lại các điều kiện quan trọng vì dữ liệu có thể đã cũ, tài nguyên liên quan có thể thay đổi hoặc một request khác đã cập nhật draft.

## 10. Đồng thời, nhiều tab và gửi lại request

Người dùng có thể mở cùng một wizard trong hai tab, nhấn nút nhiều lần hoặc gửi lại request do mạng chậm. Ứng dụng cần xác định cách xử lý những tình huống này.

**Nhiều tab:** dùng một `flowId` hoặc `draftId` riêng cho từng quy trình. Không dựa vào một session attribute duy nhất nếu người dùng có thể mở nhiều wizard song song.

**Cập nhật đồng thời:** dùng optimistic locking với trường `version` hoặc `updatedAt`. Khi request gửi version cũ, server phát hiện draft đã thay đổi và yêu cầu tải lại hoặc xử lý xung đột thay vì âm thầm ghi đè dữ liệu mới.

**Gửi lại bước cuối:** thao tác hoàn tất cần idempotent. Có thể lưu idempotency key hoặc đặt unique constraint cho việc tạo nghiệp vụ từ một draft để request lặp không tạo hai đăng ký, đơn hàng hoặc giao dịch.

**Đi sai thứ tự:** Service phải kiểm tra trạng thái hiện tại trước khi lưu bước. Không cho phép gửi bước 3 khi draft vẫn ở `STEP_1`, kể cả client tự tạo request.

## 11. Bảo mật dữ liệu wizard

Biểu mẫu nhiều bước giữ dữ liệu lâu hơn một request, vì vậy bề mặt rủi ro cũng lớn hơn.

- **Xác thực ở mỗi request:** session hoặc draft ID không tự chứng minh người dùng còn đăng nhập.
- **Kiểm tra quyền sở hữu:** mọi thao tác đọc, sửa, tiếp tục, hủy hoặc hoàn tất draft phải kiểm tra user hiện tại có quyền trên draft.
- **Chống CSRF:** các request thay đổi trạng thái cần CSRF protection khi dùng cookie/session authentication.
- **Allowlist trường binding:** chỉ bind các trường của bước hiện tại; trạng thái, owner, ID, version và thời hạn do server quản lý.
- **Không tin hidden field:** `draftId`, `currentStep`, `ownerId` hoặc giá trị giá tiền gửi từ client đều phải được kiểm tra lại.
- **Giảm thiểu dữ liệu:** chỉ giữ thông tin cần thiết cho quy trình; mã hóa hoặc bảo vệ dữ liệu nhạy cảm theo yêu cầu.
- **Không ghi dữ liệu nhạy cảm vào log:** log ID tương quan và sự kiện quy trình thay vì toàn bộ nội dung form.

Với draft có thể tiếp tục sau đăng xuất, cần yêu cầu xác thực lại khi người dùng quay lại. Nếu dùng liên kết tiếp tục qua email, token phải có entropy cao, thời hạn ngắn, chỉ dùng theo mục đích rõ ràng và được lưu an toàn ở dạng hash nếu phù hợp.

## 12. Hủy quy trình và hoàn tất

Người dùng cần có cách hủy wizard. Khi hủy, server xác minh quyền sở hữu, chuyển trạng thái sang `CANCELLED` hoặc xóa dữ liệu tạm theo chính sách, rồi kết thúc session state nếu có.

Khi hoàn tất, Service cần thực hiện các bước trong transaction ngắn:

1. Tải draft và khóa hoặc kiểm tra version phù hợp.
2. Xác minh owner, trạng thái, thời hạn và bước cuối.
3. Kiểm tra lại dữ liệu và quy tắc nghiệp vụ.
4. Tạo đối tượng nghiệp vụ chính thức.
5. Đánh dấu draft hoàn tất hoặc lên lịch xóa theo retention policy.
6. Ghi idempotency result để request lặp không tạo giao dịch mới.

Không giữ transaction mở trong lúc người dùng đọc trang review và quyết định. Transaction chỉ nên bao quanh thao tác lưu cuối cần tính nguyên tử.

## 13. Kiểm thử biểu mẫu nhiều bước

Kiểm thử cần bao phủ cả chuyển trạng thái, dữ liệu được giữ và thời hạn tồn tại:

| Tình huống | Kết quả mong đợi |
|---|---|
| Bắt đầu wizard | Tạo trạng thái mới ở bước đầu và hiển thị form tương ứng |
| Bước 1 hợp lệ | Lưu dữ liệu, chuyển sang bước 2 |
| Bước 1 không hợp lệ | Giữ giá trị và hiển thị lỗi; không chuyển bước |
| Truy cập trực tiếp bước 2 khi chưa hoàn tất bước 1 | Từ chối hoặc chuyển về bước hợp lệ |
| Quay lại bước 1 | Hiển thị dữ liệu đã lưu; cập nhật phụ thuộc nếu cần |
| Bước cuối thành công | Tạo nghiệp vụ đúng một lần và xóa/đóng wizard state |
| Session hết hạn | Không tiếp tục bằng trạng thái thiếu; hướng dẫn bắt đầu lại |
| Draft hết hạn | Từ chối cập nhật và đánh dấu/hiển thị hết hạn |
| Người dùng khác truy cập draft ID | Từ chối theo chính sách quyền truy cập |
| Hai tab cập nhật cùng draft | Phát hiện version cũ hoặc xử lý xung đột có chủ đích |
| Gửi lại request hoàn tất | Không tạo bản ghi nghiệp vụ trùng |
| Hủy wizard | Dữ liệu tạm được đóng hoặc xóa theo chính sách |

Unit test cho Service kiểm tra chuyển trạng thái và quy tắc nghiệp vụ. Test Controller kiểm tra routing, binding, view và redirect. Integration test kiểm tra session, persistence, transaction, optimistic locking, CSRF và cơ chế dọn draft hết hạn.

## 14. Những sai lầm thường gặp

- **Giữ toàn bộ wizard trong request model:** dữ liệu biến mất sau response.
- **Dùng flash attributes làm kho tiến trình:** flash chỉ phù hợp với dữ liệu ngắn hạn qua redirect.
- **Lưu wizard trong session vô thời hạn:** làm tăng dữ liệu tồn đọng và có thể giữ thông tin cá nhân quá lâu.
- **Dùng một session attribute cho nhiều wizard song song:** các tab có thể ghi đè dữ liệu của nhau.
- **Tin `currentStep` hoặc `ownerId` từ client:** người dùng có thể sửa request và bỏ qua bước hoặc truy cập draft của người khác.
- **Tạo Entity nghiệp vụ chưa hợp lệ sau mỗi bước:** làm trạng thái miền chứa dữ liệu dở dang; hãy dùng draft/form model riêng.
- **Giữ transaction qua nhiều màn hình:** gây lock lâu và giữ connection trong thời gian người dùng suy nghĩ.
- **Chỉ validation ở từng bước:** dữ liệu và điều kiện liên quan có thể thay đổi trước khi hoàn tất; cần kiểm tra cuối.
- **Không có cơ chế hết hạn và cleanup:** bản nháp không còn sử dụng vẫn tồn tại mãi.
- **Không chống request lặp:** thao tác cuối có thể tạo nhiều bản ghi.
- **Không kiểm tra quyền ở mọi request:** một draft ID khó đoán không thay thế authorization.

## 15. Kết luận

Biểu mẫu nhiều bước là một quy trình có trạng thái, chuyển đổi và thời hạn tồn tại dữ liệu. Với wizard ngắn, session có thể giữ Form DTO giữa các request; với quy trình dài hoặc cần tiếp tục trên nhiều thiết bị, database draft thường phù hợp hơn. Dù chọn cách nào, server phải kiểm soát bước hiện tại, quyền sở hữu, validation, thời hạn và việc hoàn tất.

Khi thiết kế wizard trong MVC, hãy mô hình hóa state machine trước, chọn nơi lưu dữ liệu theo thời gian người dùng cần, xác định cách xử lý quay lại và nhiều tab, rồi đặt chính sách hết hạn, cleanup, bảo mật và idempotency. Đối tượng nghiệp vụ chính thức chỉ nên được tạo khi toàn bộ dữ liệu đã được kiểm tra và quy trình được xác nhận.

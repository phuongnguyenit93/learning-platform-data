# Xử lý lỗi binding an toàn (Binding failure handling)

Binding là quá trình chuyển dữ liệu đầu vào thành các giá trị hoặc đối tượng mà ứng dụng sử dụng. Lỗi có thể xuất hiện khi một trường sai kiểu, thiếu dữ kiện bắt buộc, có cấu trúc không hợp lệ hoặc không thuộc hợp đồng.

Trong bối cảnh mass assignment, nguy hiểm không chỉ là trả mã lỗi sai. Một binder có thể đã gán một số thuộc tính trước khi gặp lỗi. Nếu đối tượng đích là entity đang được quản lý, một collection có quan hệ lưu trữ hoặc principal dùng cho phân quyền, phần thay đổi dở dang có thể ảnh hưởng nghiệp vụ dù response báo thất bại.

Bài học thuộc chương **Mass Assignment** trong bảo mật logic nghiệp vụ. Trọng tâm là bảo đảm binding thất bại không tạo ra một command được chấp nhận, không lưu dữ liệu một phần và không làm mất các ranh giới quyền, trạng thái, giá hay idempotency.

## 1. Phân biệt lỗi binding với các loại lỗi khác

| Loại lỗi | Ví dụ | Ý nghĩa |
|---|---|---|
| Đọc hoặc parse | Body bị cắt, cú pháp không hợp lệ | Chưa có cấu trúc đầu vào đáng tin để diễn giải |
| Cấu trúc hợp đồng | Field lạ, tên trùng, object thay vì danh sách | Không khớp hình dạng mà thao tác cho phép |
| Binding hoặc chuyển kiểu | expectedVersion là chuỗi không chuyển được thành kiểu được nhận | Không tạo đủ giá trị theo hợp đồng |
| Validation giá trị | quantity bằng 0 trong khi yêu cầu số dương | Đã diễn giải được nhưng giá trị không hợp lệ |
| Quyền hoặc tham chiếu | productId thuộc tenant khác | Đầu vào đúng cấu trúc chưa chứng minh được phép dùng |
| Guard nghiệp vụ | Đơn đã được duyệt nên không được sửa nháp | Trạng thái hoặc bất biến không cho phép |
| Lưu trữ, cạnh tranh | Version đã đổi, lỗi ghi hoặc commit chưa rõ | Kết quả thực thi cần xử lý theo transaction và hợp đồng |
| Lỗi lập trình hoặc cấu hình | Mapper dùng sai kiểu nội bộ | Không nên tự quy thành lỗi người dùng |

Một ứng dụng có thể nhóm một số lỗi khác nhau trong API. Tuy nhiên, bên trong cần giữ đủ phân loại để không tiếp tục xử lý một đầu vào chưa hoàn chỉnh hoặc che lỗi hệ thống thành dữ liệu mặc định.

### 1.1. Ví dụ lệnh sửa đơn nháp

Hợp đồng cho phép:

```json
{
  "expectedVersion": 17,
  "purpose": "Thiết bị cho nhóm triển khai",
  "lines": [
    { "productId": "PRD-10", "quantity": 2 }
  ]
}
```

Request sau có thể chỉ bind được một phần:

```json
{
  "expectedVersion": "khong-phai-version",
  "purpose": "Nội dung đã đổi",
  "lines": [
    { "productId": "PRD-10", "quantity": "nhieu" }
  ],
  "status": "APPROVED"
}
```

Ứng dụng phải chặn việc thực hiện lệnh. Không dùng purpose đã bind, thay version bằng 0, bỏ dòng lỗi rồi vẫn lưu phần còn lại.

Status không thuộc command sửa nội dung; nó không được gán vào domain ngay cả khi cuối cùng binder trả một danh sách lỗi.

### 1.2. Có lỗi không bảo đảm đối tượng chưa bị thay đổi

Một binder có thể xử lý tuần tự hoặc thu thập nhiều lỗi trong khi vẫn gán các trường đọc được.

Không nên suy ra:

```text
BindingResult có lỗi
    → mọi đối tượng vẫn giữ nguyên
```

Cần biết binder đã chạm vào đâu, setter có tác dụng gì và đối tượng có nằm trong persistence context hay không. Cách tốt hơn là thiết kế để binding chỉ tác động lên dữ liệu đầu vào cô lập.

## 2. Hợp đồng thất bại: không có command hoàn chỉnh thì không thực hiện

Với một lệnh nghiệp vụ đơn, chính sách minh họa là:

```text
Bất kỳ lỗi parse, cấu trúc, binding hoặc validation bắt buộc
    → không gọi luồng thay đổi nghiệp vụ
    → không tạo kết quả thành công
    → trả lỗi an toàn theo hợp đồng
```

Các bất biến cần giữ:

1. Đối tượng bind lỗi không được dùng như một command hoàn chỉnh.
2. Không có trường đã bind được nào được lưu như một phần thành công ngoài hợp đồng.
3. Tenant, danh tính, role và quyền không bị ghi đè bởi binding.
4. Owner, trạng thái, giá và các trường máy chủ quản lý không được nhận qua đường bind rộng.
5. Không phát sự kiện thành công hoặc tác dụng ngoài trước khi biết lệnh hợp lệ và được chấp nhận.
6. Lỗi lưu hoặc commit không bị che thành một lần binding thành công.
7. Retry phải bắt đầu từ dữ liệu và ngữ cảnh phù hợp, không tái dùng đối tượng đã bị làm bẩn.
8. Dấu vết từ chối được phân biệt với audit nghiệp vụ thành công.

### 2.1. Không “cứu” lệnh bằng mặc định nguy hiểm

| Cách dự phòng | Nguy cơ |
|---|---|
| Version sai thì dùng 0 hoặc version mới nhất | Mất điều kiện chống dữ liệu cũ |
| Số tiền sai thì dùng 0 | Có thể tạo giao dịch miễn phí hoặc sai hạn mức |
| Role sai thì dùng role đặc biệt để tiếp tục | Biến lỗi đầu vào thành vượt quyền |
| Owner không bind được thì giữ giá trị từ body khác | Mất nguồn có thẩm quyền hoặc sai đối tượng |
| Danh sách lỗi thì dùng danh sách rỗng | Có thể xóa toàn bộ quan hệ hoặc bỏ bước bắt buộc |
| Bỏ từng field lỗi rồi cập nhật field còn lại | Thực hiện ý định khác với request gốc |

Giá trị mặc định hợp lệ phải được hợp đồng định nghĩa cho trường hợp phù hợp, thường là một lựa chọn vắng mặt được phép. Nó không tự là cách xử lý mọi giá trị đã gửi nhưng không diễn giải được.

### 2.2. Validation không hoàn tác binding

Một kiểm tra giá trị chạy sau binding có thể phát hiện lỗi, nhưng không tự khôi phục entity, collection hoặc dịch vụ đã bị setter và converter tác động.

Tương tự, một annotation hoặc danh sách lỗi không bảo đảm controller sẽ dừng. Luồng gọi cần có cổng chặn rõ, được kiểm chứng trên đường nhận request thật.

## 3. Cô lập đối tượng đầu vào khỏi domain và principal

Một pipeline nên tách các giai đoạn:

```text
Raw input
    → cấu trúc đã parse theo giới hạn
    → input bind hoàn chỉnh
    → command đã kiểm tra giá trị
    → thay đổi đã được phân quyền và kiểm tra nghiệp vụ
    → dữ liệu được lưu và commit
```

Thất bại ở một giai đoạn không được tạo ra giá trị giả như thể đã vượt qua giai đoạn đó.

### 3.1. Bind vào DTO riêng cho từng ý định

Ví dụ command sửa nháp chỉ có:

```text
expectedVersion
purpose
lines[].productId
lines[].quantity
```

Không bind vào entity có owner, tenant, status, approvedBy hoặc assignment bảo mật. Không bind vào principal rồi dùng chính các thuộc tính vừa nhận để kiểm tra quyền.

DTO cũng không nên chứa tham chiếu mutable tới entity đã tải. Một DTO mới nhưng giữ collection của entity vẫn có thể làm thay đổi domain trong quá trình bind.

### 3.2. Kiểm tra đầy đủ cấu trúc

Schema cần xác định root, object con, kiểu phần tử, field được nhận, required, null và giới hạn.

Tên trùng hoặc alias xung đột cần được phát hiện trước khi parser hoặc mapper làm mất thông tin. Không để tầng kiểm tra thấy một giá trị nhưng tầng lưu dùng giá trị khác.

Trường ngoài hợp đồng phải được xử lý tường minh. Trong mô hình nghiêm của bài, chúng làm lệnh thất bại trước tác dụng nghiệp vụ.

### 3.3. Converter không nên có tác dụng nghiệp vụ

Converter nên diễn giải thành ID hoặc value phù hợp, không tự:

- Lưu hoặc cập nhật một entity.
- Thay owner, cấp role hoặc chuyển trạng thái.
- Gửi email, phát message hay gọi thanh toán.
- Tăng bộ đếm sử dụng nghiệp vụ như một lần đã được chấp nhận.
- Tải một đối tượng toàn cục rồi gắn vào graph mà bỏ scope tenant.

Một phép tra cứu tham chiếu hoặc kiểm tra quyền cần được đặt trong luồng có ngữ cảnh phù hợp. Không biến việc đọc một chuỗi thành hành động thay đổi domain trước khi toàn bộ lệnh được kiểm tra.

Constructor của value object có thể kiểm tra giá trị cục bộ. Nó không nên khởi chạy workflow hoặc phát sự kiện thành công chỉ vì parser đang thử tạo một ứng viên đầu vào.

## 4. Ví dụ Java: kết quả binding không chứa giá trị dở dang

Các đoạn mã sau minh họa hợp đồng bằng Java. Những kiểu reader, schema và path là cổng trừu tượng, không phải cấu hình của một thư viện cụ thể.

Một kết quả có thể chỉ có hai dạng hợp lệ:

```text
thành công: có input hoàn chỉnh, không có lỗi binding

thất bại: có lỗi, không có input để caller dùng tiếp
```

### 4.1. Kiểu kết quả chặn việc dùng đối tượng lỗi

```java
record FieldIssue(String code, InputPath path) {}

record BindingOutcome<T>(
        Optional<T> value,
        List<FieldIssue> issues) {

    BindingOutcome {
        Objects.requireNonNull(value);
        issues = List.copyOf(issues);

        if (value.isPresent() && !issues.isEmpty()) {
            throw new IllegalArgumentException(
                    "VALUE_AND_BINDING_ERRORS_CANNOT_COEXIST");
        }

        if (value.isEmpty() && issues.isEmpty()) {
            throw new IllegalArgumentException(
                    "BINDING_OUTCOME_MUST_HAVE_VALUE_OR_ERRORS");
        }
    }

    static <T> BindingOutcome<T> complete(T value) {
        return new BindingOutcome<>(
                Optional.of(value), List.of());
    }

    static <T> BindingOutcome<T> failed(List<FieldIssue> issues) {
        return new BindingOutcome<>(
                Optional.empty(), issues);
    }

    T requireComplete() {
        if (!issues.isEmpty()) {
            throw new InvalidCommandInput(issues);
        }
        return value.orElseThrow();
    }
}
```

Tên kiểu không tự bảo đảm dữ liệu đúng. Binder phải thực sự chỉ tạo value khi hoàn tất các kiểm tra thuộc trách nhiệm của nó.

Lỗi constructor do dùng sai hợp đồng kết quả là lỗi lập trình, không nên bị một khối bắt lỗi chung biến thành field không hợp lệ của client.

### 4.2. Binder chỉ tạo dữ liệu mới, không chạm domain

```java
record LineInput(String productId, int quantity) {}

record UpdateDraftInput(
        long expectedVersion,
        String purpose,
        List<LineInput> lines) {}

BindingOutcome<UpdateDraftInput> bindUpdateDraft(byte[] rawBody) {
    RawJsonObject root = bodyReader.readStrictObject(
            rawBody, requestLimits);

    List<FieldIssue> issues = new ArrayList<>();

    draftSchema.collectStructuralIssues(root, issues);

    Long expectedVersion = fieldReaders.requiredLong(
            root, "expectedVersion", issues);

    String purpose = fieldReaders.requiredText(
            root, "purpose", issues);

    List<LineInput> lines = lineReader.readRequiredLines(
            root, "lines", issues);

    if (!issues.isEmpty()) {
        return BindingOutcome.failed(issues);
    }

    UpdateDraftInput input = new UpdateDraftInput(
            expectedVersion,
            purpose,
            List.copyOf(lines));

    return BindingOutcome.complete(input);
}
```

Hợp đồng các helper:

- Reader áp dụng giới hạn và không làm mất những dữ kiện mà schema cần để phát hiện tên trùng.
- Schema kiểm tra đầy đủ field được nhận ở root và object con, cùng các cấu trúc bắt buộc.
- Field bắt buộc không có hoặc sai kiểu phải ghi lỗi hoặc dừng bằng lỗi đầu vào đã phân loại; không trả một giá trị mặc định kèm kết quả thành công.
- Khi không còn lỗi, các giá trị bắt buộc phải đầy đủ và đúng kiểu để tạo input.
- Line reader có thể dùng biến cục bộ trong quá trình đọc, nhưng không trả một danh sách “chỉ gồm dòng tốt” như thể toàn bộ lệnh đã hoàn chỉnh.
- Không helper nào giữ tham chiếu tới entity, principal hoặc collection dùng chung với domain.
- Lỗi parse không thể phục hồi an toàn phải kết thúc đường đọc; không đoán tiếp nội dung.

Thành công ở đây chỉ nghĩa binding hoàn chỉnh theo schema và kiểu. Validation giá trị, quyền, tham chiếu và bất biến nghiệp vụ vẫn cần các bước tiếp theo.

### 4.3. Adapter dừng trước handler

```java
ApiResponse updateDraft(
        String requestIdFromPath,
        byte[] rawBody,
        VerifiedRequest verifiedRequest) {

    BindingOutcome<UpdateDraftInput> outcome =
            inputBinder.bindUpdateDraft(rawBody);

    UpdateDraftInput input = outcome.requireComplete();

    ValidatedUpdateDraft command = commandFactory.validateAndCreate(
            requestIdFromPath, input);

    DraftUpdated result = draftHandler.handle(
            verifiedRequest, command);

    return presenter.updated(result);
}
```

Exception adapter có thể chuyển `InvalidCommandInput` hoặc lỗi parse đã phân loại thành response phù hợp. Nó không gọi handler trong nhánh lỗi.

RequestId được lấy theo hợp đồng đường dẫn, còn verifiedRequest được tạo từ đường xác thực có thẩm quyền. Body không được bind vào hai dữ kiện đó.

Cần kiểm soát mọi đường gọi handler. Nếu một controller khác vẫn truyền DTO có lỗi, việc có kiểu ValidatedUpdateDraft ở một chỗ chưa đủ.

## 5. Transaction và entity được quản lý

### 5.1. Vì sao trả lỗi bình thường có thể vẫn lưu?

Mã giả dễ gặp:

```java
return transactions.required(() -> {
    PurchaseRequest managed = requests.findForUpdate(id);

    BindReport report = unsafeBinder.bindInto(rawBody, managed);

    if (report.hasErrors()) {
        return errorResponse(report);
    }

    return successResponse();
});
```

Nếu đối tượng nằm trong persistence context có theo dõi thay đổi, những thuộc tính đã bị binder sửa có thể được flush khi transaction commit.

Việc trả một response lỗi là một lần return bình thường trong đoạn mã. Nó không tự bảo đảm transaction adapter sẽ rollback. Hành vi rollback cần được cấu hình và kiểm chứng theo cơ chế đang dùng.

Không gọi repository.save không đồng nghĩa không có câu ghi nào. Cascade, thay đổi collection hoặc flush có thể làm graph bị ghi theo mô hình persistence.

### 5.2. Thiết kế tránh làm bẩn entity ngay từ đầu

Một cách sắp xếp:

```text
Ngoài phần thay đổi domain:
    đọc body theo giới hạn
    kiểm tra cấu trúc
    bind DTO cô lập
    validation đầu vào

Trong transaction nghiệp vụ:
    tải đối tượng đúng tenant
    kiểm tra quyền hiện tại
    kiểm tra version, state và dữ kiện liên quan
    tính nội dung từ nguồn có thẩm quyền
    áp dụng thay đổi tường minh
    lưu cùng audit, outbox và kết quả lệnh nếu áp dụng
    commit
```

Việc phân quyền một số loại request hoặc kiểm tra credential có thể cần diễn ra sớm hơn. Điểm chính là binding không tự sửa graph nghiệp vụ trước khi lệnh đủ điều kiện.

### 5.3. Nếu hệ thống cũ đã bind vào entity

Cần chặn lưu dở dang và sửa kiến trúc theo phạm vi thực tế. Tối thiểu phải biết tất cả đối tượng đã bị chạm và bảo đảm transaction tương ứng không commit khi binding thất bại.

Không nên coi các thao tác sau là giải pháp tự động đầy đủ:

- Bắt exception rồi return lỗi mà không giữ ngữ nghĩa rollback.
- Gọi save trong finally.
- Detach hoặc xóa persistence context rồi cho rằng các câu ghi đã flush sẽ tự bị hoàn tác.
- Gán lại vài trường nhạy cảm nhưng bỏ sót collection hoặc thuộc tính mới.
- Tái dùng chính entity dở dang cho lần thử tiếp theo.
- Chỉ khôi phục bảng gốc trong khi quan hệ con đã thay đổi.

Rollback cơ sở dữ liệu cũng không thu hồi email hoặc lệnh bên ngoài đã gửi. Vì vậy converter, setter và callback của đường binding không nên tạo các tác dụng đó.

### 5.4. Lỗi commit không phải lỗi binding

Có thể bind thành công nhưng lỗi phát sinh khi ghi hoặc commit. Không trả thành công trước khi transaction adapter xác nhận theo hợp đồng.

Nếu lỗi do version, cần xử lý xung đột. Nếu kết quả commit chưa rõ do kết nối, cần đối soát bằng định danh lệnh trước khi lặp. Nếu do cấu hình hay lỗi lập trình, cần đường lỗi hệ thống.

Không gom mọi exception sau binding thành một mã “sai dữ liệu đầu vào”, vì client và vận hành sẽ không biết cách xử lý đúng.

## 6. Object lồng nhau, collection và tham chiếu

### 6.1. Không chia sẻ collection giữa DTO và entity

Một DTO có field lines nhưng trỏ tới cùng danh sách với entity vẫn có thể gây sửa domain trong lúc đọc đầu vào.

Cần giữ dữ liệu đầu vào cô lập, rồi tạo thay đổi được kiểm tra. Việc sao chép nông một graph cũng có thể còn giữ các object con mutable dùng chung.

Với persistence có cascade hoặc quản lý quan hệ con, thao tác thêm, xóa hay thay collection trước khi biết toàn bộ lệnh hợp lệ có thể tạo cập nhật ngoài ý muốn.

### 6.2. Không bỏ dòng lỗi rồi đánh lại vị trí

Giả sử dòng 0 hợp lệ, dòng 1 lỗi và dòng 2 hợp lệ. Nếu bỏ dòng 1 rồi dùng vị trí còn lại để cập nhật line hiện có, hệ thống có thể sửa sai dòng.

Với lệnh đơn trong bài, một dòng lỗi làm cả command không hợp lệ. Đường dẫn lỗi cần giữ vị trí gốc.

Nếu payload nhận lineId, phải kiểm tra line đó thuộc đúng parent và tenant. Một ID chuyển kiểu thành công không chứng minh quyền cập nhật.

### 6.3. Giới hạn đường dẫn và việc tạo object tự động

Một số cơ chế bind hỗ trợ đường dẫn collection hoặc object con. Cần giới hạn path được phép, độ sâu, chỉ số và số phần tử trước khi phát triển graph không kiểm soát.

Không cho một path chỉ vì nó có thể được mapper diễn giải thành một setter. Khả năng kỹ thuật của binder rộng hơn hợp đồng nghiệp vụ.

Với field như owner, tenant hoặc security, lỗi chuyển kiểu hay giá trị null không được khiến tầng sau thử một nguồn tự khai khác rồi tiếp tục.

### 6.4. Tham chiếu nên được kiểm tra trong ngữ cảnh

Binder có thể tạo productId hoặc attachmentId dưới dạng giá trị. Việc tải và sử dụng chúng cần scope tenant, parent và quyền phù hợp.

Tránh converter trả về một entity toàn cục rồi để binder tiếp tục sửa thuộc tính bên trong. Cách đó vừa mở graph mass assignment, vừa làm mờ điểm kiểm tra quyền.

## 7. Patch, batch và nhập dữ liệu theo luồng

### 7.1. Patch không có nghĩa bỏ qua field lỗi

Một lệnh sửa từng phần có thể cho phép field vắng mặt mang nghĩa giữ nguyên. Điều đó khác với field đã gửi nhưng sai kiểu.

Ví dụ:

```text
không gửi purpose:
    giữ nguyên nếu hợp đồng cho phép

gửi purpose với kiểu không được nhận:
    lỗi, không tự diễn giải thành giữ nguyên
```

Nếu cứ bỏ field lỗi, client không biết ý định nào đã được thực hiện. Với thao tác có các trường liên quan như số tiền và tiền tệ, cập nhật một phần còn có thể phá bất biến.

Các định dạng patch cần quy tắc riêng về thao tác, path, null, nguồn và đích. Không đưa patch thẳng vào entity được quản lý trước khi biết nó có thể được áp dụng hợp lệ.

Có thể diễn giải và thử áp dụng trên một biểu diễn cô lập theo hợp đồng, kiểm tra kết quả cùng quyền, rồi mới thay đổi domain trong transaction. Bản thử không được giữ tham chiếu mutable tới domain thật.

### 7.2. Batch cần chọn đơn vị nguyên tử

Có hai hợp đồng khác nhau:

| Hợp đồng | Cách xử lý |
|---|---|
| Cả batch cùng thành công hoặc cùng thất bại | Một lỗi bắt buộc ngăn toàn bộ thay đổi của batch |
| Từng bản ghi có kết quả riêng | Mỗi bản ghi là một đơn vị được kiểm tra và lưu riêng; lỗi một bản ghi không có nghĩa được lưu nửa bản ghi đó |

Cần phân biệt lỗi của envelope với lỗi từng record. Tenant, danh tính hoặc cấu trúc bao ngoài không hợp lệ có thể khiến không thể xử lý an toàn bất kỳ record nào.

Partial success phải được thiết kế, có định danh đầu vào và kết quả rõ. Nó không nên là hệ quả tình cờ của binder bỏ dòng lỗi rồi tiếp tục.

### 7.3. Không phục hồi bằng cách đoán ranh giới dữ liệu

Khi cú pháp bao ngoài hỏng, không nên tự cắt vài byte hoặc đoán một dấu phân cách tiếp theo rồi tiếp tục các hành động nghiệp vụ.

Một cơ chế đọc theo luồng chỉ được tiếp tục khi định dạng, parser và hợp đồng đủ xác định ranh giới record cùng điều kiện phục hồi. Nếu không, các trường có thể bị gắn sang record khác.

Lỗi cấu trúc không phải lý do đổi tenant, target hoặc các giá trị điều khiển bằng mặc định.

### 7.4. Staging không phải thành công nghiệp vụ

Với đầu vào lớn, có thể cần lưu dữ liệu vào vùng staging riêng tư để parse và kiểm tra. Trạng thái đã nhận tệp hoặc đã nhận byte phải khác với đã chấp nhận các lệnh bên trong.

Chỉ những record hoặc batch vượt đầy đủ kiểm tra theo hợp đồng mới đi vào luồng ghi nghiệp vụ. Không cho worker đọc một DTO lỗi đã được đưa vào queue như thể nó là command hợp lệ.

Dữ liệu staging cần vòng đời, scope và cleanup phù hợp. Cleanup không được ghi bù các field mặc định hoặc thử lưu lại entity để “không mất phần đã nhập”.

## 8. Idempotency và retry sau binding failure

### 8.1. Không đánh dấu thành công khi chưa có lệnh

Nếu binding thất bại, hệ thống chưa có một command hoàn chỉnh theo hợp đồng. Không tạo kết quả idempotency nói rằng đơn đã được sửa hoặc quyết định đã được ghi.

Có thể lưu lần từ chối để quan sát hoặc theo một hợp đồng ghi nhớ lỗi riêng. Bản ghi đó phải thể hiện đúng thất bại, có scope rõ và không bị hiểu là quyền thực hiện lệnh.

Một idempotency key đúng cú pháp cũng không làm payload sai trở nên hợp lệ.

### 8.2. Chuẩn hóa sau khi biết dữ liệu được chấp nhận

Với endpoint nghiêm:

```text
parse và kiểm tra cấu trúc
    → bind hoàn chỉnh
    → kiểm tra giá trị thuộc trách nhiệm đầu vào
    → dựng biểu diễn command
    → tính fingerprint theo hợp đồng
```

Không xóa field lỗi, thay kiểu sai bằng mặc định rồi tính fingerprint như thể đó là ý định người dùng đã gửi.

Nếu cùng key của một lệnh trước nhưng payload mới có field ngoài hợp đồng, payload mới vẫn cần xử lý theo chính sách đầu vào. Không lấy nhánh replay để bỏ qua mọi kiểm tra cấu trúc.

Quyền xem kết quả cũ cũng cần được bảo vệ; biết key không tự tạo quyền với đối tượng.

### 8.3. Sửa request rồi dùng lại key

Điều này phụ thuộc hợp đồng:

- Nếu lệnh bind lỗi chưa chiếm key như một lệnh được chấp nhận, request đã sửa có thể được xử lý từ đầu theo quy tắc của hệ thống.
- Nếu hệ thống ghi nhớ lỗi theo key và fingerprint, việc dùng lại cần tuân thủ chính sách đó, có thể đòi một key khác.

Không trả lại thành công giả và không tự thực hiện lệnh khác dưới một key đã ràng buộc với nội dung trước.

Cần ghi rõ cho client, thay vì để hành vi phụ thuộc việc exception xuất hiện trước hay sau một dòng lưu command log tình cờ.

### 8.4. Không retry bằng graph đã bị mutate

Lỗi chuyển kiểu không phải lỗi tạm thời sẽ tự hết khi gọi lại cùng binder trên cùng entity.

Nếu retry sau lỗi kỹ thuật, cần trạng thái domain mới, quyền hiện tại và precondition phù hợp. Không tái dùng entity có các field hoặc collection đã bị gán dở.

Một command bất biến đã hợp lệ có thể được sử dụng theo hợp đồng retry, nhưng các điều kiện domain thay đổi vẫn phải được đọc và kiểm tra lại. Không tái dùng kết quả quyền hoặc giá cũ ngoài bảo đảm đã chọn.

Nếu commit chưa rõ, đối soát bằng định danh ổn định trước khi lặp tác dụng. Không kết luận đó là binding failure chỉ vì client thấy lỗi cuối cùng.

## 9. Giới hạn tài nguyên và tác dụng phụ của đường lỗi

Binding failure có thể bị tạo lặp hoặc chứa dữ liệu rất lớn. Đường lỗi cũng cần giới hạn.

Các giới hạn có thể gồm kích thước body, độ sâu, số field, số phần tử, độ dài tên, chiều dài biểu diễn số và số lỗi được thu thập.

Khi đã hết ngân sách lỗi hoặc không thể tiếp tục an toàn, dừng với kết quả thất bại. Không coi việc ngừng kiểm tra là dấu hiệu những field còn lại được phép.

### 9.1. Chuyển kiểu không được là tác vụ không giới hạn

Giá trị quá dài hoặc có độ chính xác vượt hợp đồng có thể tốn tài nguyên trước khi bị phát hiện vượt phạm vi.

Lớp đọc, bộ chuyển kiểu và validation cần phối hợp. Chỉ kiểm tra số tiền sau khi đã phân tích một biểu diễn không giới hạn có thể không đủ bảo vệ đường tiếp nhận.

Quy tắc kiểu và phạm vi phải gắn với nghiệp vụ. Không dùng truncation hoặc làm tròn tùy ý như một cách chữa mọi giá trị không bind được.

### 9.2. Không khởi chạy tác dụng theo từng field

Nếu setter hoặc converter tạo task bất đồng bộ, việc handler dừng sau đó không bảo đảm task đó dừng.

Không gửi thông báo, cấp quyền, giữ chỗ hay gọi hệ thống ngoài trong quá trình chỉ đang cố diễn giải đầu vào. Các tác dụng phải nằm sau kiểm tra tương ứng và trong giao thức nhất quán đã chọn.

Với tích hợp ngoài, rollback cục bộ không đủ. Có thể cần ghi ý định bền vững sau khi lệnh hợp lệ rồi để thành phần thực thi xử lý theo hợp đồng.

### 9.3. Finally chỉ làm công việc phù hợp với đường thất bại

Đóng stream hoặc giải phóng tài nguyên cục bộ có thể phù hợp trong finally. Gọi save, phát sự kiện thành công hoặc tiếp tục một workflow ở đó có thể làm lỗi binding trở thành thay đổi nghiệp vụ.

Tệp tạm hoặc staging cần được dọn đúng phạm vi sở hữu và trạng thái. Không dùng một đường dẫn chưa kiểm tra từ payload lỗi để xóa tài nguyên.

## 10. Phản hồi lỗi và audit an toàn

Một phản hồi có thể là:

```json
{
  "code": "INVALID_COMMAND_INPUT",
  "errors": [
    {
      "code": "TYPE_MISMATCH",
      "path": "$.expectedVersion"
    },
    {
      "code": "TYPE_MISMATCH",
      "path": "$.lines[0].quantity"
    }
  ],
  "correlationId": "CORR-707"
}
```

Không cần trả lại toàn bộ DTO dở dang để giúp client sửa lỗi. Một giá trị đã bind được vẫn có thể chứa thông tin không nên phản chiếu hoặc khiến client nghĩ nó đã được lưu.

### 10.1. Phân loại để xử lý đúng

| Tình huống | Hành vi phù hợp |
|---|---|
| Cú pháp hoặc kiểu không được nhận | Báo lỗi đầu vào đã phân loại, không gọi nghiệp vụ |
| Thiếu hoặc sai giá trị bắt buộc | Báo đường dẫn theo hợp đồng |
| Không đủ quyền hoặc ngoài tenant | Phản hồi theo chính sách truy cập, không tiết lộ dữ liệu ngoài scope |
| Version hoặc trạng thái đã đổi | Báo xung đột hoặc điều kiện nghiệp vụ theo API |
| Mapper hoặc schema nội bộ lỗi | Lỗi hệ thống và chẩn đoán nội bộ |
| Lưu hoặc commit chưa rõ | Đối soát, không báo binding thành công hoặc thất bại giả |

Mã HTTP có thể khác tùy hợp đồng; cần nhất quán và không dùng một khối bắt mọi exception để biến tất cả thành lỗi field.

### 10.2. Không phản chiếu rejected value tùy ý

Field lỗi có thể chứa mật khẩu, token, dữ liệu cá nhân, nội dung rất dài hoặc ký tự điều khiển.

Nên trả mã lỗi và đường dẫn được định dạng an toàn; chỉ phản hồi giá trị khi có lý do và chính sách rõ. Không mặc định serialize mọi thuộc tính của một lỗi binder.

Tên path do đầu vào ảnh hưởng cũng cần escape, giới hạn và biểu diễn theo cấu trúc. Không cho một field lạ tạo các dòng log giả.

### 10.3. Giữ nguyên nhân mà không tiếp tục xử lý

Chỉ chuyển những lỗi parse hoặc chuyển kiểu được nhận diện thành lỗi client. Một lỗi null nội bộ hay lỗi cơ sở dữ liệu không nên bị nuốt rồi tiếp tục với DTO mặc định.

Có thể thu thập nhiều field issue trong giới hạn, nhưng kết quả vẫn là thất bại nếu có lỗi bắt buộc. Không coi một số field đọc được là lý do cho phép handler chạy.

Audit từ chối cần khác với audit “đã cập nhật”. Nếu transaction rollback, dấu vết thành công không được tồn tại như một lần commit hợp lệ. Đường quan sát từ chối cần được thiết kế để không biến mất ngoài ý muốn cùng rollback.

Không ghi toàn bộ payload hoặc graph để điều tra một lỗi binding. Cần giữ đủ endpoint, hợp đồng, mã lỗi, đường dẫn an toàn và correlationId theo phạm vi truy cập.

## 11. Giữ cùng chính sách ở mọi adapter

Một nghiệp vụ có thể đi qua controller, form, import, message hoặc công cụ quản trị. Mỗi adapter phải tạo command theo cùng giới hạn cần thiết.

Không bảo vệ JSON bằng DTO riêng rồi để một form binder hoặc consumer bind thẳng entity.

Các lớp dùng chung nên giúp bảo đảm:

- Đường lỗi không cung cấp partial value cho caller.
- Việc chuyển exception có phân loại và không gọi handler tiếp.
- Schema, converter và validator đồng ý về tên, kiểu, null và required.
- Những field máy chủ quản lý không được mở vì entity hoặc DTO khác được thêm thuộc tính.
- Các helper không có tác dụng nghiệp vụ hoặc tham chiếu mutable dùng chung.
- Transaction và đường phản hồi giữ đúng ngữ nghĩa commit.
- Kết quả batch thể hiện đúng đơn vị nguyên tử.

Cần kiểm thử qua đường nhận dữ liệu thật. Một test gọi validator trên DTO được tạo sẵn không chứng minh binder đã ngăn field lạ, tên trùng hoặc setter có tác dụng phụ.

Khi nâng phiên bản mapper hoặc thay cấu hình, cần xác nhận các bảo đảm này vẫn đúng. Nhãn “strict” hoặc “validated” không tự thay thế hành vi thực tế.

## 12. Kiểm thử binding failure và tác dụng còn sót

### 12.1. Ma trận tình huống

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Field đầu bind được, field sau sai kiểu | Không lưu field đầu như một phần thành công |
| Version bắt buộc thiếu hoặc sai kiểu | Không dùng mặc định để bỏ điều kiện cạnh tranh |
| Field status, owner hoặc role ngoài command | Không đi vào domain hoặc principal |
| Object con có field ngoài hợp đồng | Không chỉ chặn ở root |
| Dòng cuối của danh sách lỗi | Không lưu dòng trước trong lệnh nguyên tử |
| Tên trùng hoặc alias xung đột | Phát hiện trước khi mất thông tin |
| Danh sách null, rỗng và thiếu | Có hành vi riêng đúng hợp đồng |
| Reference đúng kiểu nhưng ngoài tenant | Bị chặn ở bước quyền và tham chiếu phù hợp |
| Binder có target là entity được quản lý | Kiểm thử phát hiện mọi khả năng ghi dở dang; đường an toàn không dùng target đó |
| DTO giữ collection dùng chung | Không cho thay đổi đầu vào tác động domain trước cổng kiểm tra |
| Converter thử ghi hoặc phát message | Không có tác dụng từ đường binding |
| Request dùng path collection rất lớn | Bị giới hạn trước phát triển graph không kiểm soát |
| Patch có thao tác sau không hợp lệ | Không giữ tác dụng trước trong lệnh nguyên tử |
| Batch có một record lỗi | Đúng hợp đồng toàn bộ hoặc từng record, không nửa record |
| Envelope batch không diễn giải được | Không đoán tenant, target hoặc ranh giới để tiếp tục |
| Cùng key nhưng payload mới bind lỗi | Không tạo kết quả thành công mới hoặc làm mất kết quả cũ |
| Mapper ném lỗi lập trình | Không nuốt thành DTO mặc định rồi tiếp tục |
| Lỗi khi ghi hoặc commit | Không gắn nhãn như một lần binding thành công đã hoàn tất |
| Error object chứa dữ liệu nhạy cảm | Phản hồi và log không serialize tùy ý |
| Adapter import hoặc message dùng cùng nghiệp vụ | Không có đường bind rộng hơn controller chính |

### 12.2. Một ca phát hiện lưu dở dang

Chuẩn bị một đơn nháp có purpose và các dòng hàng đã biết.

Gửi request gồm:

```json
{
  "expectedVersion": "sai-kieu",
  "purpose": "Nội dung không được lưu",
  "lines": [
    { "productId": "PRD-10", "quantity": 3 },
    { "productId": "PRD-11", "quantity": "khong-hop-le" }
  ],
  "status": "APPROVED"
}
```

Kỳ vọng:

```text
response lỗi theo hợp đồng
purpose trong nguồn dữ liệu vẫn là giá trị trước
mọi dòng hàng vẫn giữ nguyên
state, owner, tenant, rowVersion và contentRevision không đổi
không có quyết định hoặc execution mới
không có outbox báo cập nhật thành công
không có tác dụng bên ngoài
```

Ca này cần đi qua reader, binder, adapter và transaction thực tế. Chỉ kiểm tra một danh sách lỗi không chứng minh dữ liệu chưa bị ghi.

### 12.3. Đọc lại sau ranh giới transaction

Với persistence có dirty tracking, cần kiểm tra từ nguồn sau khi transaction xử lý request đã kết thúc, bằng một ngữ cảnh đọc phù hợp.

Không chỉ nhìn object trong bộ nhớ vừa bị bind. Cũng không để transaction tự rollback của bộ test che việc handler thật đã coi return lỗi là một đường commit.

Kiểm thử nên làm rõ ranh giới của test và request. Nếu request tham gia một transaction bao ngoài do test giữ, kết quả có thể khác luồng chạy thật.

Ngoài bảng gốc, cần kiểm tra bảng con, quan hệ, audit thành công, outbox và các dấu vết tác dụng liên quan.

### 12.4. Chèn lỗi ở các điểm quan trọng

Các điểm đáng kiểm tra:

1. Reader gặp lỗi sau một phần body hợp lệ.
2. Binder đọc được purpose nhưng không tạo được version.
3. Line reader có danh sách ứng viên cục bộ nhưng một phần tử lỗi.
4. Validation đầu vào thất bại sau binding hoàn chỉnh.
5. Guard nghiệp vụ thất bại trước hoặc trong quá trình áp dụng.
6. Cập nhật root thành công trong transaction nhưng bước ghi child hoặc audit lỗi.
7. Commit thành công nhưng response bị mất.
8. Đường ghi telemetry từ chối gặp lỗi.

Với lỗi đầu vào, không được tới thay đổi nghiệp vụ. Với lỗi transaction, rollback phải giữ các bất biến tương ứng. Với commit chưa rõ, không thực hiện lại tác dụng trước khi đối soát theo hợp đồng.

Lỗi telemetry không được biến một input không hợp lệ thành lệnh được phép.

### 12.5. Kiểm thử hợp đồng kết quả binding

Nếu dùng kiểu kết quả như ví dụ:

- Kết quả thất bại không có partial value.
- Kết quả thành công không kèm field issue chưa xử lý.
- Không thể tạo kết quả trống cả value lẫn lỗi như một thành công ngầm.
- Helper bắt buộc không im lặng trả null hoặc giá trị mặc định khi sai kiểu.
- Lỗi cấu hình helper không bị biến thành một command rỗng.
- Adapter không gọi handler khi requireComplete thất bại.

Đây là các kiểm tra ranh giới, không chỉ kiểm tra một câu if. Cần bổ sung test qua từng adapter thật có thể gọi cùng handler.

## 13. Bài tập áp dụng

Thiết kế đường sửa nội dung đơn nháp có danh sách dòng hàng và version kỳ vọng.

1. Phân loại lỗi parse, cấu trúc, chuyển kiểu, validation, quyền và lưu trữ.
2. Chọn đơn vị nguyên tử cho lệnh đơn, patch và batch.
3. Thiết kế DTO cùng kết quả binding không lộ đối tượng dở dang cho handler.
4. Xác định các helper và converter phải thuần, không trả tham chiếu entity.
5. Vẽ ranh giới transaction để lỗi không làm bẩn root hoặc collection.
6. Định nghĩa phản hồi an toàn và hành vi idempotency khi request được sửa sau lỗi.
7. Chỉ ra cách adapter khác có thể vô tình bind rộng hơn và cách ngăn.
8. Viết test phát hiện dirty flush sau return lỗi bằng một lần đọc độc lập.
9. Liệt kê những thay đổi và tác dụng phải vắng mặt sau mỗi lần từ chối.

Binding failure được xử lý đúng khi nó kết thúc việc diễn giải một lệnh chưa hợp lệ mà không để phần dữ liệu đọc được trở thành thay đổi nghiệp vụ. Cô lập input, chặn rõ trước handler và giữ đúng ranh giới transaction giúp bảo vệ các quy tắc về quyền, trạng thái, giá trị và tính toàn vẹn của đối tượng.

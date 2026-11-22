# Mass assignment test — Kiểm thử ghi thuộc tính ngoài thẩm quyền

## 1. Kiểm thử điều gì khi kiểm thử mass assignment?

Một endpoint có thể cho khách hàng sửa ghi chú đơn hàng nhưng không cho đổi chủ sở hữu, tenant, giá chốt, trạng thái thanh toán hoặc bằng chứng phê duyệt. Mass assignment xuất hiện khi dữ liệu đầu vào tác động được đến những thuộc tính ngoài hợp đồng ghi của action.

Vì vậy, mục tiêu kiểm thử không chỉ là gửi thêm `isAdmin=true` rồi xem HTTP status. Cần chứng minh rằng **mọi thay đổi được nhận đều nằm trong thẩm quyền của chủ thể, trên đúng đối tượng, đúng trạng thái và đúng tập thuộc tính được phép**.

Một kết luận có giá trị cần trả lời:

- Người gọi có thực sự được phép dùng action với payload hợp lệ không?
- Payload đã đi qua đúng parser, binder và mapper của hệ thống chưa?
- Các field ngoài hợp đồng có bị từ chối hoặc bị bỏ qua đúng chính sách không?
- Dữ liệu lưu, quan hệ đối tượng, command và hiệu ứng bên ngoài có thay đổi trái phép không?
- Những đường khác như PATCH, import hoặc queue có giữ cùng ranh giới không?

Bài học sử dụng các endpoint đơn hàng giả định để minh họa cách xây test trong Java. Các payload và đoạn code là tình huống kiểm thử cho ứng dụng do nhóm phát triển kiểm soát, không phải kết quả đã chạy trên một hệ thống cụ thể.

## 2. Định nghĩa hợp đồng trước khi viết assertion

Giả sử có action:

```text
PATCH /orders/{orderId}/draft-note
```

Hợp đồng của ví dụ chỉ nhận:

```json
{
  "expectedVersion": 18,
  "customerNote": "Giao trong giờ làm việc"
}
```

Actor phải có quyền sửa ghi chú trên order còn ở `DRAFT`. Tenant, owner, giá, trạng thái và thông tin thanh toán do những nguồn hoặc action khác quản lý.

### 2.1. Hai chính sách field lạ khác nhau

| Chính sách | Request có field ngoài hợp đồng | Kết quả cần kiểm tra |
| --- | --- | --- |
| Từ chối | Không áp dụng request | Lỗi đúng hợp đồng, không có thay đổi nghiệp vụ được nhận |
| Bỏ qua | Chỉ áp dụng phần input hợp lệ được cho phép | Những field ngoài hợp đồng không gây tác động trực tiếp hoặc gián tiếp |

Ví dụ code trong bài chọn chính sách từ chối với mã công khai `FIELD_NOT_ALLOWED`. Đây là lựa chọn hợp đồng của ví dụ, không phải kết luận mọi API an toàn đều phải trả cùng status hoặc cùng mã.

Nếu một API công bố bỏ qua field lạ và trả `200` mà không có thay đổi trái phép, không thể chỉ dựa vào status đó để kết luận có lỗ hổng. Ngược lại, một API trả lỗi nhưng đã ghi dữ liệu hoặc tạo tác vụ trái phép vẫn không đạt yêu cầu.

### 2.2. Phân biệt field có thể ghi với field dẫn xuất

Ở action sửa số lượng, tổng tiền có thể phải được server tính lại. Không nên assert rằng mọi field không có trong payload đều bất biến.

Cần có danh mục tác động được phép: input nào được nhận, dữ liệu nào được tính lại, quan hệ nào được phép thay và event nào có thể phát sinh. Các assertion phải dựa trên hợp đồng đó.

## 3. Xây ma trận kiểm thử từ danh mục trường ghi

Một ma trận đầu tiên có thể gồm:

| Nhóm thuộc tính | Ví dụ cần thử theo model thực tế | Bất biến cần chứng minh |
| --- | --- | --- |
| Miền dữ liệu | `tenantId`, `organizationId` | Không chuyển sang miền ngoài quyền |
| Sở hữu | `ownerId`, `createdBy` | Không nhận quyền hoặc đổi trách nhiệm trái phép |
| Phân quyền | `roleIds`, `permissions`, cờ quản trị | Không mở năng lực ngoài action |
| Vòng đời | `state`, `approved`, `cancelledAt` | Không đi tắt state machine |
| Bằng chứng phê duyệt | `approvedBy`, `approvalId`, `approvalRound` | Không giả hoặc tái gắn quyết định |
| Tiền và giá | `unitPriceMinor`, `discountMinor`, `paidAmountMinor` | Chỉ nguồn được phép quyết định số tiền |
| Quan hệ | ID dòng, địa chỉ, tài khoản hoặc chứng từ | Không cập nhật hay gắn đối tượng ngoài phạm vi |
| Cờ điều khiển | `force`, `skipApproval`, `onBehalfOf` | Không bỏ guard hoặc giả actor |
| Dữ liệu mở rộng | `metadata`, object con, map | Không biến dữ liệu tùy biến thành thuộc tính có thẩm quyền |

Danh sách này là điểm xuất phát, không phải payload cố định áp dụng cho mọi API. Cần dùng những tên và đường dẫn thực sự có thể đến binder, mapper hoặc những bước xử lý sau của ứng dụng.

### 3.1. Đừng chỉ kiểm tra field nổi tiếng

Một ứng dụng không có `isAdmin` vẫn có thể có `approvalBypass`, `riskLevel`, `effectiveTenant` hoặc một quan hệ cấp quyền khác. Bề mặt kiểm thử phải xuất phát từ model, hợp đồng action và những nơi input được sử dụng.

### 3.2. Không dùng entity làm chuẩn duy nhất

Một field không được lưu trực tiếp vẫn có thể đổi phạm vi hoặc tạo hiệu ứng. Ví dụ `includeAllTenants`, `callbackUrl` hay `sendPaymentNow` có thể điều khiển service mà không là cột của order.

Test cần theo dõi cả tác động nghiệp vụ, không chỉ những setter trên entity.

## 4. Trường hợp đối chứng hợp lệ là bắt buộc

Trước mỗi nhóm mutation, phải có một request nền mà actor được phép thực hiện và hệ thống thực sự nhận đúng.

Nếu request nền đã bị `401`, `403`, lỗi CSRF, sai media type hoặc version cũ, thêm field cấm rồi nhận lại lỗi không chứng minh ranh giới field đang hoạt động.

Một fixture cho action sửa note có thể chứa:

```text
Tenant A và tenant B.
Actor U là người được sửa order O thuộc A.
Một người khác V và một order khác P để thử tham chiếu.
O ở DRAFT, version 18, note có giá trị đã biết.
Owner, giá chốt và trạng thái thanh toán của O có giá trị đã biết.
```

Request hợp lệ phải chứng minh được:

- Note đổi sang giá trị mới.
- Version tăng theo hợp đồng.
- Owner, tenant, trạng thái và dữ liệu tài chính không bị đổi bởi action này.
- Chỉ có những event hoặc command được phép cho việc đổi note.

### 4.1. Actor phải phù hợp mục tiêu test

Để kiểm tra field-level protection, dùng actor có quyền gọi action trên đối tượng. Các test actor không có quyền vẫn cần, nhưng chúng kiểm tra một hàng rào khác.

Không dùng một tài khoản toàn quyền cho mọi test vì nó có thể làm mất điều kiện mà người dùng thông thường phải tuân thủ. Nếu có hợp đồng quản trị riêng, kiểm tra riêng hợp đồng đó và giới hạn của nó.

### 4.2. Giá trị giả mạo phải đúng kiểu

Nếu field mục tiêu là UUID mà test gửi chuỗi `abc`, request có thể bị chặn chỉ do lỗi parse. Để kiểm tra quyền ghi, dùng một ID đúng định dạng và, khi cần, một đối tượng tham chiếu thực sự tồn tại trong fixture.

Với enum, dùng giá trị hợp lệ của domain. Với số tiền hoặc boolean, chọn giá trị có nghĩa theo kiểu dữ liệu thay vì chỉ gửi dữ liệu hỏng.

## 5. Tạo payload thô để không mất field cần kiểm tra

Một lỗi viết test thường gặp là tạo request bằng chính DTO production. Nếu DTO không có field cấm, serializer không thể gửi field đó; test chưa từng chạm vào input mà kẻ gọi HTTP có thể tự tạo.

Hãy tạo JSON tree hoặc chuỗi JSON có kiểm soát rồi chèn mutation:

```java
ObjectNode body = json.createObjectNode();
body.put("expectedVersion", 18L);
body.put("customerNote", "Giao trong giờ làm việc");
body.put("state", "APPROVED");

byte[] requestBytes = json.writeValueAsBytes(body);
```

Payload vẫn phải đủ hợp lệ để đi đến hàng rào cần kiểm tra. Một lỗi cú pháp JSON không chứng minh `state` đã được bảo vệ.

### 5.1. Mutation từng field

Bắt đầu bằng một field ngoài hợp đồng mỗi lần. Điều này giúp xác định field, path và lớp kiểm soát gây ra kết quả.

Sau đó thêm một số tổ hợp có ý nghĩa nghiệp vụ. Một request chỉ đổi `state` có thể bị một guard khác chặn, trong khi tổ hợp `state`, `approvedBy` và dữ liệu liên quan lại đáp ứng một kiểm tra yếu phía sau.

Không cần tạo mọi tổ hợp không giới hạn. Chọn tổ hợp theo những bất biến và nguồn quyền cần bảo vệ.

### 5.2. Key trùng cần chuỗi raw riêng

JSON tree thông thường chỉ giữ một giá trị cho mỗi key, nên không thể dùng nó để chứng minh cách parser xử lý key trùng.

Nếu hợp đồng yêu cầu từ chối cấu trúc mơ hồ, test trường hợp đó bằng raw bytes phù hợp. Kết quả chỉ có ý nghĩa cho chính sách parser đã chọn; không giả định mọi parser hoặc lớp trung gian diễn giải key trùng giống nhau.

## 6. Kiểm tra dữ liệu thật, không chỉ response

Một response có thể che field bảo vệ trong khi database đã bị đổi. Hoặc API trả `400` sau khi một event đã được đưa vào hàng đợi.

Một snapshot trước request nên bao phủ tập dữ liệu liên quan đến bất biến đang kiểm tra:

| Nguồn quan sát | Ví dụ cần xem |
| --- | --- |
| Đối tượng chính | Tenant, owner, state, version, note, tổng tiền |
| Entity và quan hệ con | Dòng hàng, địa chỉ được gắn, người nhận |
| Dữ liệu phân quyền | Assignment hoặc quan hệ quyền nếu payload có thể chạm tới |
| Workflow | Approval, execution command, reservation |
| Event bền vững | Outbox hoặc lệnh nghiệp vụ được nhận |
| Tích hợp ngoài | Lời gọi tới stub thanh toán hoặc tích hợp liên quan |
| Dữ liệu tenant khác trong fixture | Không bị đổi khi thử tham chiếu ngang |

Không nhất thiết snapshot toàn bộ cơ sở dữ liệu. Hãy chọn phạm vi đủ để chứng minh tác động được phép và bị cấm của action.

### 6.1. Phân biệt audit lần thử với hiệu ứng thành công

Request bị từ chối có thể hợp lệ tạo sự kiện an ninh về field không được phép. Vì vậy assertion “không có bất kỳ log hoặc event nào” có thể sai.

Cần chặn những hiệu ứng không được nhận, chẳng hạn `OrderApproved`, `PaymentRequested` hoặc một success audit giả. Audit lần thử bị từ chối có thể được cho phép theo hợp đồng riêng.

### 6.2. Đọc lại bằng ngữ cảnh mới

Không chỉ xem lại entity đang nằm trong cache của test. Probe nên đọc trạng thái có thẩm quyền bằng transaction hoặc persistence context phù hợp để không bỏ sót dữ liệu đã được mapper ghi.

Với tác vụ bất đồng bộ, kiểm tra command hoặc outbox bền vững và chạy worker theo cơ chế test có điều khiển nếu cần xác minh hiệu ứng. Không chờ một khoảng `sleep` tùy ý rồi kết luận không có công việc nào xuất hiện.

## 7. Ví dụ Java: test HTTP với chính sách từ chối field lạ

### 7.1. Giả định

Ví dụ dùng Spring Boot test và MockMvc để đi qua HTTP binding, validation, controller, service và persistence của ứng dụng kiểm thử.

- Endpoint dùng xác thực session và có kiểm tra CSRF trong mô hình ví dụ.
- Fixture cấp principal đúng tenant và đúng quyền tối thiểu cho action.
- Cấu hình binding và mapper cần tương ứng đường production được kiểm tra.
- Dữ liệu fixture đã commit trước request, không dựa vào một transaction bao ngoài toàn test.
- Các dependency tạo hiệu ứng ngoài được thay bằng stub có thể quan sát.

Các helper bên dưới là thành phần cần xây trong test suite của dự án. Đoạn mã không phải một bộ test độc lập có thể chạy ngay.

### 7.2. Test đối chứng và mutation

```java
@SpringBootTest
@AutoConfigureMockMvc
class DraftNoteMassAssignmentIT {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired MassAssignmentFixtures fixtures;
    @Autowired BusinessStateProbe state;
    @Autowired BusinessEffectProbe effects;

    @Test
    void ownerCanChangeOnlyTheAllowedNote() throws Exception {
        OrderFixture f = fixtures.ownerEditableDraft();
        BusinessSnapshot before = state.capture(f);
        EffectCheckpoint checkpoint = effects.checkpoint(f);

        ObjectNode body = validNoteBody(f);

        mvc.perform(patch("/orders/{id}/draft-note", f.orderId())
                .with(f.ownerAuthentication())
                .with(csrf())
                .header("Idempotency-Key", UUID.randomUUID().toString())
                .contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsBytes(body)))
            .andExpect(status().isOk());

        state.assertOnlyNoteAndDeclaredDerivedFieldsChanged(
                f, before, "Giao trong giờ làm việc");
        effects.assertOnlyDeclaredNoteEffects(f, checkpoint);
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "state", "tenantId", "ownerId", "paidAmountMinor"
    })
    void rejectsProtectedRootField(String field) throws Exception {
        OrderFixture f = fixtures.ownerEditableDraft();
        BusinessSnapshot before = state.capture(f);
        EffectCheckpoint checkpoint = effects.checkpoint(f);

        ObjectNode body = validNoteBody(f);
        body.set(field, f.validForgedValueFor(field));

        mvc.perform(patch("/orders/{id}/draft-note", f.orderId())
                .with(f.ownerAuthentication())
                .with(csrf())
                .header("Idempotency-Key", UUID.randomUUID().toString())
                .contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsBytes(body)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("FIELD_NOT_ALLOWED"));

        state.assertBusinessStateUnchanged(f, before);
        effects.assertNoNewAcceptedBusinessEffects(f, checkpoint);
    }

    private ObjectNode validNoteBody(OrderFixture f) {
        ObjectNode body = json.createObjectNode();
        body.put("expectedVersion", f.orderVersion());
        body.put("customerNote", "Giao trong giờ làm việc");
        return body;
    }
}
```

Các import JUnit, Spring test, Jackson và thư viện assertion tương ứng cần được khai báo trong dự án. `validForgedValueFor()` phải trả giá trị đúng kiểu; với ID, dùng đối tượng thực trong fixture theo tình huống, không dùng chuỗi hỏng để test chỉ thắng nhờ parser.

`assertBusinessStateUnchanged()` cần bao phủ những entity và quan hệ bảo vệ đã xác định. `assertNoNewAcceptedBusinessEffects()` không cấm audit từ chối được phép, nhưng phải phát hiện command hoặc event thành công trái hợp đồng.

Helper authentication không được âm thầm cấp role quản trị rộng hoặc tắt security để làm request đi qua. Test này tập trung ranh giới field qua HTTP; việc xác minh credential và claim production cần những kiểm thử tương ứng riêng.

### 7.3. Vì sao không bọc toàn bộ test trong một transaction?

Nếu request MockMvc chạy cùng thread và tham gia transaction test, thao tác có thể chưa commit như request thực. Việc test tự rollback cuối cùng cũng có thể che một thiết kế đã ghi dữ liệu trước khi trả lỗi.

Hãy để ranh giới transaction của request được thực thi theo mô hình cần kiểm tra, dùng dữ liệu fixture được chuẩn bị và dọn theo cơ chế phù hợp. Probe đọc lại trạng thái sau request để chứng minh commit hoặc rollback thực sự.

## 8. Kiểm thử nested object và collection ở endpoint thực sự nhận chúng

Test thêm `unitPriceMinor` vào một endpoint chỉ nhận note có thể bị chặn ngay ở root. Nó chưa chứng minh parser của một endpoint có `lines` cũng bảo vệ đúng field con.

Cần một đối chứng riêng cho action nhận các dòng hàng hợp lệ, sau đó mutate đúng object con:

```java
ObjectNode body = f.validDraftInputsBody(json);
ArrayNode lines = (ArrayNode) body.get("lines");
ObjectNode firstLine = (ObjectNode) lines.get(0);
firstLine.put("unitPriceMinor", 1L);

// Gửi tới endpoint draft-inputs, không phải endpoint chỉ nhận note.
// Sau đó kiểm tra hợp đồng lỗi hoặc bỏ qua, dữ liệu dòng, quote,
// trạng thái order và mọi hiệu ứng được tạo.
```

Những path cần xem xét theo schema thực tế:

```text
lines[*].unitPriceMinor
lines[*].approvedDiscount
shippingContact.verificationStatus
owner.id
owner.roles[*].id
metadata.effectiveTenant
```

Không cần giả định mọi ứng dụng đều có các path đó. Mục tiêu là tìm những object và quan hệ thực sự được bind, nhất là khi dùng mapper hoặc entity graph dùng chung.

### 8.1. Kiểm tra quan hệ, không chỉ field đơn

Với line ID hoặc address ID, thử:

- Đối tượng cùng tenant nhưng thuộc order hoặc khách hàng khác.
- Đối tượng thuộc tenant khác.
- Một ID hợp lệ nhưng actor không được sử dụng.

Payload có thể không chứa field nhạy cảm như `tenantId` mà vẫn tạo truy cập ngang nếu backend gắn một quan hệ chỉ dựa trên ID.

### 8.2. Không bỏ quên những phần tử sau

Một kiểm tra chỉ áp dụng cho dòng đầu tiên có thể bỏ lọt field cấm hoặc ID khác tenant ở dòng sau. Đặt mutation ở đầu, giữa, cuối hoặc ở một vị trí được sinh có kiểm soát trong giới hạn hỗ trợ.

## 9. Kiểm thử null, field thiếu và mặc định ghi đè

Mass assignment không chỉ là thêm field. Mapper quá rộng còn có thể ghi đè dữ liệu bảo vệ bằng giá trị mặc định khi field vắng mặt.

Ma trận cần có:

| Dạng input | Điều cần kiểm tra |
| --- | --- |
| Field bảo vệ bị bỏ hoàn toàn | Không bị đặt null, false hoặc giá trị mặc định |
| Field bảo vệ gửi null | Không được xóa ngoài hợp đồng |
| Field bảo vệ gửi false hoặc 0 | Không được đổi chỉ vì giá trị có vẻ vô hại |
| Object con rỗng | Không xóa hoặc thay các quan hệ bảo vệ ngoài ý định |
| Collection rỗng | Chỉ xóa khi action và trạng thái cho phép |
| Field được phép bị bỏ trong PATCH | Xử lý đúng nghĩa không sửa của hợp đồng |
| Field được phép gửi null | Chỉ xóa nếu phép xóa đã được cho phép |

Đối với endpoint PUT thay thế một phần input, kiểm tra field nào thuộc phần biểu diễn được thay và field nào luôn do server giữ. Không suy ra tên method HTTP cho phép ghi đè toàn bộ entity.

## 10. Kiểm thử các dạng PATCH và kênh binding khác

### 10.1. Payload patch dạng object

Kiểm tra path được phép, path ngoài hợp đồng và candidate cuối sau khi áp dụng. Một patch có thể kết hợp những field riêng lẻ hợp lệ để làm mất một điều kiện bắt buộc, nên cần kiểm tra bất biến của candidate cuối.

### 10.2. Patch có danh sách operation

Nếu API hỗ trợ `add`, `replace`, `remove`, `copy`, `move` hoặc `test`, cần test đúng từng operation được công bố.

Ví dụ những câu hỏi kiểm thử:

- Có thay được `state` qua `replace` dù DTO cập nhật thường không có field đó không?
- Có xóa được field bắt buộc bằng `remove` không?
- Có copy từ một path được bảo vệ sang path có thể đọc để lộ dữ liệu không?
- Có move quan hệ làm đổi owner hoặc tenant không?
- Có dùng `test` để suy đoán giá trị một field ngoài quyền đọc không?

Mỗi operation cần xét cả nguồn, đích, quyền và điều kiện trạng thái. Một thư viện patch đúng cú pháp không tự cấp quyền đúng theo nghiệp vụ.

### 10.3. Form, multipart và import

Nếu một đường vào thực sự hỗ trợ form binding hoặc import, kiểm tra tên property mà đường đó hiểu, kể cả dot notation, chỉ số mảng hoặc cột tùy biến khi có.

Không coi `415 Unsupported Media Type` ở một endpoint không hỗ trợ form là bằng chứng đã kiểm tra form binder của endpoint khác. Test phải đúng kênh có thể ghi dữ liệu.

### 10.4. Message và lớp xử lý về sau

Một field bị bỏ qua ở API có thể được giữ trong raw payload rồi mapper của worker dùng lại. Cần đưa mutation qua đúng chuỗi xử lý và quan sát command, entity hoặc lời gọi bên ngoài cuối cùng.

Chữ ký message hoặc danh tính service chỉ xác thực nguồn theo cơ chế tương ứng. Nó không biến toàn bộ property trong message thành dữ liệu được phép ghi vào mọi đối tượng.

## 11. Kiểm thử giá, quyền và transition bằng bất biến cụ thể

### 11.1. Giá và số tiền

Nếu client được sửa số lượng nhưng không sửa giá, test cần chứng minh:

```text
giá được nhận = kết quả nguồn định giá được phép
không phải giá hoặc tổng tiền giả trong payload
```

Khi quantity thay đổi hợp lệ, total có thể thay đổi. So sánh với quote có thẩm quyền của tình huống kiểm thử, không mặc định total phải giữ nguyên.

Kiểm tra currency, discount hoặc cờ override nếu chúng có thể đến đường ghi. Một giá thấp hợp lệ về kiểu vẫn không phải quyền đặt giá.

### 11.2. Phê duyệt và trạng thái

Thêm `approved=true`, `approvedBy` hoặc state đích không được tạo quyết định phê duyệt hoặc command thực thi. Cần xem cả bảng approval, vòng duyệt, snapshot nội dung và outbox liên quan.

Một response vẫn hiển thị `DRAFT` không đủ nếu backend đã tạo một bản ghi approval sẽ được worker dùng về sau.

### 11.3. Quyền và sở hữu

Khi thử role, owner hoặc delegation field, kiểm tra quyền hiệu lực sau request chứ không chỉ cột role trực tiếp. Quan hệ nhóm, hierarchy hoặc grant có thể bị tạo qua một mapper con.

Actor thật trong audit phải không bị thay bằng `createdBy`, `approvedBy` hoặc `onBehalfOf` do caller tự khai ngoài hợp đồng.

## 12. Chính sách bỏ qua: dùng phép so sánh với đối chứng

Nếu API chủ động bỏ qua field ngoài hợp đồng, assertion lỗi `400` không phù hợp. Có thể so sánh hai lần chạy trên fixture tương đương:

```text
Control: chỉ có input hợp lệ.
Mutant:  cùng input hợp lệ, thêm field ngoài hợp đồng.

Kỳ vọng: các hiệu ứng nghiệp vụ được nhận tương đương nhau
theo những dữ liệu canonical mà hợp đồng cho phép.
```

Cần giữ rõ:

- Những field bảo vệ vẫn có cùng ý nghĩa và giá trị đúng theo fixture.
- Input hợp lệ vẫn được xử lý đúng.
- Không có command hoặc quan hệ mới do field ngoài hợp đồng.
- Audit có thể ghi thêm dấu vết lần thử theo chính sách, nhưng không giả thành hiệu ứng nghiệp vụ hợp lệ.

### 12.1. Không chuẩn hóa đến mức xóa mất bằng chứng

Hai fixture có thể có ID hoặc timestamp khác nhau. Có thể đối chiếu bằng ánh xạ fixture được biết, nhưng không được bỏ toàn bộ ID, owner, tenant hoặc version khỏi phép so sánh chỉ để test xanh.

Những thuộc tính đó chính là phần cần bảo vệ. So sánh phải giữ quan hệ đúng với actor, tenant và đối tượng, không chỉ làm JSON trông giống nhau.

### 12.2. Hành vi bỏ qua phải đúng đến cuối luồng

Một response có thể bỏ field trong khi raw body được lưu lại để import lần nữa. Đối chứng cần quan sát đúng thời điểm các bước được thiết kế sẽ dùng dữ liệu đó.

Nếu không thể thực thi toàn luồng trong một test, tách các kiểm thử có ràng buộc rõ giữa message được phát và consumer nhận. Không kết luận đầu cuối chỉ từ việc serializer response không có field cấm.

## 13. State machine, quyền và version có thể che hoặc làm lộ lỗi

### 13.1. Test từng hàng rào với tiền đề hợp lệ

Một field giá giả có thể bị che bởi lỗi order đã khóa. Một ID khác tenant có thể bị che bởi credential không hợp lệ. Một mutation có thể bị che bởi expected version sai.

Để chứng minh hàng rào field, các điều kiện không thuộc mục tiêu test nên được đáp ứng. Sau đó viết những test riêng cho quyền trên đối tượng và trạng thái.

### 13.2. Kiểm tra nhiều trạng thái có ý nghĩa

Một mapper có thể chỉ chạy ở một nhánh, chẳng hạn cập nhật draft khác cập nhật hồ sơ đã duyệt. Cần chọn trạng thái mà code thực sự có thể xử lý, không thử một trạng thái bất khả rồi cho rằng đã bao phủ toàn bộ.

Với state được bảo vệ, kiểm tra request không thể tự đặt `DRAFT` để mở quyền sửa một order đang `APPROVED`, cũng không thể ghi đè snapshot được duyệt bằng input cũ.

### 13.3. Concurrency cần lịch có điều khiển

Ví dụ:

```text
T1 đọc hoặc khóa order để sửa input.
T2 gửi duyệt hoặc thay quyền sở hữu.
T1 tiếp tục ghi.
```

Test phải chứng minh giao thức khóa hoặc version không cho phép ghi trên trạng thái khác với tiền đề đã kiểm tra. Dùng transaction độc lập cùng barrier hoặc latch; không dựa vào `sleep` để hy vọng hai luồng đụng nhau.

Việc field nằm trong allowlist không làm nó luôn được ghi ở mọi trạng thái.

## 14. Chọn tầng test và môi trường phù hợp

| Tầng | Bắt được điều gì? | Giới hạn |
| --- | --- | --- |
| Unit test mapper hoặc factory | Tập thuộc tính được ánh xạ, phép tính và điều kiện cục bộ | Không chứng minh parser HTTP hoặc cấu hình binding thực tế |
| Test domain service | Quyền, state machine, candidate và ràng buộc logic | Có thể bỏ sót việc field lạ đã lọt qua một kênh khác |
| Test HTTP tích hợp | Parser, DTO, mapper, handler và đường ghi được nối với nhau | Không tự bao phủ mọi import hoặc consumer |
| Test persistence thực | Constraint, quan hệ, optimistic concurrency và transaction | Không tự kiểm tra credential hoặc proxy ngoài ứng dụng |
| Test worker hoặc tích hợp ngoài | Command, message và hiệu ứng được xử lý cuối cùng | Cần fixture và kiểm soát delivery phù hợp |

Không cần mọi test đều chạy toàn hệ thống. Cần phối hợp các tầng để mỗi bảo đảm quan trọng có bằng chứng đúng chỗ.

### 14.1. Đừng thay bộ phận đang muốn kiểm tra bằng mock

Nếu mục tiêu là tìm mapper copy thừa field, mock mapper rồi trả một entity an toàn sẽ bỏ mất bề mặt lỗi. Nếu mục tiêu là kiểm tra binding, gọi trực tiếp service với một DTO đã lọc sẵn không đủ.

Mock hoặc stub nên đặt ở ranh giới phù hợp, chẳng hạn nhà cung cấp thanh toán, trong khi giữ đường nhận input và ghi dữ liệu cần kiểm tra.

### 14.2. Giữ những khác biệt môi trường có ý nghĩa

Cấu hình parser, naming strategy, field lạ, cascade và transaction của test cần phản ánh đường production. Một profile test rộng quyền hơn hoặc một mapper khác có thể làm kết quả không đại diện.

Với kiểm thử constraint và concurrency, dùng engine dữ liệu có hành vi phù hợp với môi trường triển khai. Một cơ sở dữ liệu thay thế có thể không tái hiện đúng các đặc tính cần chứng minh.

## 15. Sinh mutation có giới hạn và kiểm tra chất lượng test

### 15.1. Sinh từ inventory, không chỉ từ implementation hiện tại

Có thể tạo tập mutation theo loại field, path, kiểu giá trị và trạng thái. Tập đó nên dựa trên chính sách nghiệp vụ và những dữ liệu cần bảo vệ, không chỉ tự đọc allowlist hiện tại rồi kiểm tra rằng code tuân theo chính allowlist đó.

Nếu allowlist đã sai nhưng cả generator và assertion đều dùng nó làm chân lý, test vẫn có thể xanh.

### 15.2. Biến đổi từng yếu tố

Từ input hợp lệ, lần lượt:

1. Thêm một field bảo vệ với giá trị đúng kiểu.
2. Thêm field đó vào một object con hợp lệ.
3. Thay một selector bằng ID ngoài phạm vi.
4. Dùng null hoặc bỏ field để tìm mặc định ghi đè.
5. Dùng alias hoặc kênh binding thực sự được hỗ trợ.
6. Tạo một tổ hợp nhất quán có thể vượt một kiểm tra cục bộ yếu.

Giới hạn kích thước và số trường hợp để test có thể lặp lại, chẩn đoán được và không biến thành một quá trình fuzz không có tiêu chí kết thúc.

### 15.3. Thử làm hỏng kiểm soát trong môi trường kiểm thử

Một cách đánh giá suite là cố ý đưa vào một thay đổi dễ gây ghi thừa trong bản dựng kiểm thử cô lập, chẳng hạn mở một mapping ngoài hợp đồng, rồi kiểm tra suite có phát hiện tác động không.

Cần chọn mutation thực sự chạm được đường cần kiểm tra. Nếu một lớp bảo vệ độc lập vẫn chặn hoàn toàn payload, việc test không thất bại chưa tự chứng minh suite yếu; phải phân tích mutation còn có thể tạo hành vi trái hợp đồng hay không.

Không đưa cấu hình nới bảo vệ hoặc endpoint phục vụ mutation vào môi trường người dùng. Mục tiêu là đo khả năng phát hiện của test, không tạo một đường vận hành mới.

## 16. Diễn giải kết quả và ghi nhận bằng chứng

### 16.1. Những kết quả dễ bị hiểu sai

| Quan sát | Không được kết luận vội |
| --- | --- |
| `403` | Có thể chỉ thiếu quyền action hoặc CSRF, chưa kiểm tra field |
| `400` | Có thể sai kiểu hoặc cú pháp, chưa chứng minh boundary đúng |
| `415` | Kênh không được hỗ trợ ở endpoint đó, không nói về binder khác |
| `409` | Có thể version cũ hoặc trạng thái không phù hợp |
| `500` | Không phải một cơ chế chặn đạt yêu cầu; cần kiểm tra lỗi và trạng thái dữ liệu |
| `200` | Có thể đúng với chính sách bỏ qua hoặc có lỗ hổng; cần xem hiệu ứng |
| Response không có field cấm | Database hoặc worker vẫn có thể đã dùng nó |

Một lỗi hệ thống không nên được coi là test thành công chỉ vì không thấy giá trị giả trong response. Hợp đồng lỗi và khả năng rollback cũng cần đúng.

### 16.2. Bằng chứng của một lỗi thực sự

Một ghi nhận nên có:

- Action, actor, scope và trạng thái đối tượng dùng làm tiền đề.
- Request đối chứng hợp lệ cùng kết quả mong đợi.
- Mutation tối thiểu làm xuất hiện tác động ngoài hợp đồng.
- Dữ liệu trước và sau hoặc command được tạo trái phép.
- Hàng rào bị vượt và bất biến nghiệp vụ bị vi phạm.
- Các kênh, vai trò và trạng thái đã kiểm tra trong phạm vi kết luận.

Không cần đưa credential, token, dữ liệu khách hàng thật hoặc toàn bộ database vào báo cáo. Dùng fixture và bằng chứng tối thiểu đủ tái hiện vấn đề.

### 16.3. Phân biệt lỗi hợp đồng với quyền ghi trái phép

Nếu API hứa từ chối field lạ nhưng lại bỏ qua an toàn, đó có thể là lỗi hợp đồng hoặc khả năng chẩn đoán. Cần mô tả đúng, không nâng thành lỗ hổng thay đổi dữ liệu nếu không có bằng chứng tác động.

Nếu field không được ghi nhưng lại được dùng để gửi tiền, đổi tenant truy vấn hoặc tạo quyền ở bước sau, đây vẫn là tác động trái phép cần xử lý dù entity chính không thay đổi.

## 17. Ma trận kiểm tra trước khi kết luận

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Request nền có được nhận không? | Đối chứng hợp lệ với actor, media type và version đúng |
| Payload có thực sự chứa mutation không? | Raw bytes hoặc JSON tree không đi qua DTO lọc trước |
| Mutation có đúng kiểu không? | Giá trị hợp lệ theo loại field và fixture tham chiếu |
| Chính sách là từ chối hay bỏ qua? | Hợp đồng endpoint và assertion phù hợp |
| Có kiểm tra dữ liệu lưu không? | Probe mới sau request, gồm quan hệ quan trọng |
| Có kiểm tra tác động về sau không? | Outbox, command, worker hoặc stub tích hợp liên quan |
| Có bao phủ nested input không? | Endpoint và object con thực sự được hỗ trợ |
| Field vắng mặt có gây ghi đè không? | Test null, mặc định và ngữ nghĩa PATCH |
| Có giữ tenant và quyền theo đối tượng không? | Fixture khác owner, khác order và khác tenant |
| Test có phản ánh transaction thật không? | Request không bị che bởi transaction test bao ngoài |
| Model mới có tự mở quyền không? | Kiểm tra field mới và mapping thay đổi theo inventory |
| Kết luận có đúng phạm vi không? | Ghi rõ đường vào, trạng thái và bất biến đã kiểm tra |

Ma trận này phục vụ tính đúng đắn của kiểm thử. Nó không thay thế danh mục field và quy tắc nghiệp vụ riêng của hệ thống.

## 18. Bài tập xây bộ test

Thiết kế bộ test cho ba action: sửa note bản nháp, thay danh sách SKU và số lượng, yêu cầu gửi duyệt. Client không được ghi tenant, owner, giá, trạng thái hoặc bằng chứng phê duyệt.

Hãy mô tả:

1. Payload đối chứng và actor tối thiểu hợp lệ cho từng action là gì?
2. Field bảo vệ nào cần thử ở root, object con và phần tử mảng?
3. Chính sách field lạ là từ chối hay bỏ qua, và assertion khác nhau ra sao?
4. Những giá trị forged nào đúng kiểu và dùng đối tượng thật trong fixture để tránh lỗi parse che mất lỗi quyền?
5. Snapshot dữ liệu và probe hiệu ứng cần bao phủ bảng, quan hệ và command nào?
6. Làm sao chứng minh giá thay đổi do nguồn server chứ không do `unitPriceMinor` trong payload?
7. PATCH, import và consumer nào cần kiểm thử riêng vì dùng cơ chế mapping khác?
8. Test concurrency và test thay đổi model nào ngăn field mới âm thầm mở rộng quyền ghi?

Một bộ test đạt yêu cầu phải chứng minh hành vi từ đầu vào đến hiệu ứng nghiệp vụ: input hợp lệ vẫn làm được việc được phép, còn thuộc tính ngoài thẩm quyền không thể thay đổi dữ liệu, quyền hoặc workflow qua bất kỳ đường đã được kiểm tra nào.

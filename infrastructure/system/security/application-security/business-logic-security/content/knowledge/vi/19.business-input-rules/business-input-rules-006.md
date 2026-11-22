# Xử lý trường không xác định trong đầu vào nghiệp vụ (Unknown field handling)

Một request có thể đúng cú pháp JSON nhưng chứa những trường mà thao tác nghiệp vụ không được phép nhận. Người dùng thêm `status=APPROVED`, `ownerId` của người khác hoặc `unitPrice=1` vào body; nếu tầng ánh xạ chép chúng vào entity, ứng dụng có thể bỏ qua phê duyệt, thay quyền sở hữu hoặc làm sai giá.

Trường ngoài hợp đồng cũng có thể là lỗi vô ý: client viết sai `quantity` thành `quanity`, hoặc một phiên bản client gửi cấu trúc mà server chưa hiểu. Nếu server âm thầm bỏ qua rồi thực hiện phần còn lại, kết quả có thể khác ý định người dùng.

Bài học thuộc chương **Business Input Rules** trong bảo mật logic nghiệp vụ. Trọng tâm là xác định trường nào được nhận cho từng lệnh, xử lý trường thừa một cách tường minh và giữ cùng ngữ nghĩa qua parser, DTO, validation, transaction và idempotency.

## 1. Trường không xác định là gì?

Một trường là không xác định đối với **hợp đồng của thao tác đang xử lý**, không phải chỉ vì nó không tồn tại trong cơ sở dữ liệu.

Ví dụ endpoint sửa nội dung đơn nháp cho phép:

```http
PATCH /purchase-requests/PR-410/draft-content
Content-Type: application/json

{
  "expectedVersion": 17,
  "purpose": "Thiết bị cho nhóm triển khai",
  "lines": [
    { "productId": "PRD-10", "quantity": 2 }
  ]
}
```

Trong hợp đồng này:

- `purpose`, `lines` và `expectedVersion` là các trường được nhận.
- `status` có thể tồn tại trên entity nhưng không thuộc lệnh sửa nội dung.
- `tenantId` được xác định từ ngữ cảnh có thẩm quyền, không lấy tùy ý từ body.
- `unitPrice` có thể là dữ liệu máy chủ tính theo danh mục và chính sách của ví dụ.
- `quanity` là một tên không có trong hợp đồng.

Không nên dùng danh sách cột entity làm danh sách trường người gọi được thay đổi.

### 1.1. Những trường hợp cần phân biệt

| Trường hợp | Ví dụ | Ý nghĩa |
|---|---|---|
| Trường không xác định | `quanity` thay vì `quantity` | Không có trong hợp đồng thao tác |
| Trường có trên mô hình nhưng không được nhận | `approvedBy` trong lệnh sửa nháp | Thuộc dữ liệu phía máy chủ hoặc lệnh khác |
| Trường được nhận nhưng người gọi không có quyền thay | Một giá thương lượng trong luồng chỉ cho vai trò riêng | Cần kiểm tra quyền theo trường hoặc action |
| Trường thiếu | Không có `lines` dù hợp đồng yêu cầu | Vi phạm tính bắt buộc |
| Giá trị null | Có `lines: null` | Không đồng nghĩa vắng mặt hoặc danh sách rỗng |
| Trường trùng | Hai thành viên cùng tên trong một object | Có thể gây diễn giải khác nhau giữa các tầng |
| Alias được hỗ trợ | Hai tên hợp đồng cùng ánh xạ tới một thuộc tính | Cần chính sách chuẩn hóa và xung đột rõ |
| Vùng mở rộng được khai báo | `displayMetadata` theo schema riêng | Không phải quyền chèn thuộc tính nghiệp vụ tùy ý |

Việc xử lý lỗi có thể dùng các mã khác nhau. Điều quan trọng là mọi trường hợp đều có ngữ nghĩa được định nghĩa và không tự biến thành dữ liệu được tin cậy.

## 2. Vì sao trường thừa có thể phá vỡ logic nghiệp vụ?

### 2.1. Gán hàng loạt vào entity

Một luồng nguy hiểm:

```text
nhận JSON
    → ánh xạ trực tiếp vào entity
    → lưu entity
```

Nếu entity có setter cho owner, trạng thái hoặc hạn mức, request có thể tác động nhiều hơn mục đích endpoint.

Ví dụ:

```json
{
  "purpose": "Thiết bị văn phòng",
  "status": "APPROVED",
  "ownerSubjectId": "person-B",
  "approvedBy": "director-01"
}
```

Chỉ kiểm tra người gọi được sửa bản nháp chưa đủ nếu mapper cho họ thay cả các thuộc tính xác định quyền và vòng đời.

Nên dùng DTO hoặc command riêng, sau đó cập nhật tường minh những thuộc tính mà lệnh được phép thay. Thêm một field mới vào entity không được tự mở thêm khả năng từ API.

### 2.2. Giá và các dữ kiện có nguồn máy chủ

Trong ví dụ, dòng hàng chỉ nhận sản phẩm và số lượng. Nếu client thêm giá hoặc tỷ lệ giảm giá mà server không được phép nhận, chúng phải được xử lý theo hợp đồng.

Ngay cả khi một trường giá được khai báo hợp lệ trong nghiệp vụ khác, nó vẫn cần quyền, hạn mức và cách tính phù hợp. “Tên trường đã biết” không đồng nghĩa “giá trị do client gửi là đúng”.

### 2.3. Bỏ qua trường thừa nhưng vẫn thực hiện

Client gửi:

```json
{
  "expectedVersion": 17,
  "purpose": "Đổi thiết bị",
  "lines": [
    { "productId": "PRD-10", "quantity": 2, "unitPrice": 1 }
  ]
}
```

Nếu server bỏ `unitPrice` và dùng giá danh mục, nghiệp vụ có thể vẫn giữ đúng giá. Tuy nhiên, client có thể tưởng giá 1 đã được chấp nhận nếu phản hồi không rõ.

Nếu phần còn lại còn có thay đổi nhạy cảm, xử lý không tường minh làm khó phát hiện sai hợp đồng hoặc lần thử lạm dụng. Một chính sách nghiêm với lệnh thay đổi trạng thái thường chọn từ chối toàn bộ đầu vào không đúng hợp đồng trước khi tạo thay đổi nghiệp vụ.

### 2.4. Read-only cũng cần ngữ nghĩa

Một trường được coi là chỉ đọc phải có hành vi đầu vào rõ: bị từ chối, bị bỏ qua theo hợp đồng hoặc không có trong DTO nhận.

Không giả định rằng gắn nhãn “read-only” ở tài liệu hoặc một tầng hiển thị sẽ tự ngăn mọi mapper ghi trường đó. Cần kiểm chứng hành vi thực tế của đường xử lý.

## 3. Chọn chính sách: từ chối, bỏ qua hay vùng mở rộng

| Chính sách | Khi có thể phù hợp | Điều cần bảo vệ |
|---|---|---|
| Từ chối trường ngoài hợp đồng | Lệnh nghiệp vụ cần ý định rõ và ít chấp nhận nhập nhằng | Từ chối trước thay đổi; lỗi an toàn và có thể sửa |
| Bỏ qua trường ngoài hợp đồng | Một giao diện được thiết kế có chủ đích để dung nạp mở rộng | Trường bị bỏ qua không ảnh hưởng quyền hoặc tác dụng qua đường khác |
| Thu nhận vào vùng mở rộng | Có nhu cầu metadata tùy biến được khai báo | Schema, giới hạn và cách dùng riêng; không trộn vào thuộc tính có thẩm quyền |

Không có một lựa chọn mặc định đúng cho mọi giao thức. Cần chọn theo loại thao tác và hợp đồng phiên bản.

Trong bài này, endpoint sửa nội dung đơn nháp dùng chính sách **từ chối trường ngoài hợp đồng ở mọi object được khai báo**.

### 3.1. Bỏ qua có chủ đích không phải bỏ qua vì không biết

Nếu chọn dung nạp, phải xác định rõ phạm vi và bảo đảm:

- Một trường bị bỏ qua không được một tầng khác đọc để đổi quyền, tenant hoặc trạng thái.
- Không mapper nào vẫn giữ nó trong entity hoặc một map rồi hợp nhất về sau.
- Phản hồi và idempotency có ngữ nghĩa thống nhất với lệnh thực sự được thực hiện.
- Có giới hạn kích thước, độ sâu và số trường, kể cả phần không dùng.
- Các phiên bản và producer được kiểm thử theo hợp đồng đó.

Một request đọc hoặc tìm kiếm cũng có thể bị sai ý nghĩa khi bỏ qua tên bộ lọc viết sai. “Không ghi dữ liệu” không có nghĩa mọi trường lạ đều vô hại, nhất là với báo cáo hoặc xuất dữ liệu.

### 3.2. Vùng mở rộng phải tách khỏi dữ liệu điều khiển

Nếu cho phép metadata, hãy xác định nơi và kiểu dữ liệu cụ thể. Ví dụ metadata phục vụ nhãn hiển thị không được trở thành nguồn để tính tenant, owner, giá hoặc quyền phê duyệt.

Một key có tiền tố đặc biệt không tự an toàn. Cần giới hạn tên, kiểu giá trị, số lượng và cách tiêu thụ theo hợp đồng.

Không hợp nhất vùng mở rộng vào root bằng thao tác sao chép map. Một khóa `status` nằm trong metadata không được vô tình ghi đè status của entity.

## 4. Kiểm tra cấu trúc đầy đủ trước khi bind

### 4.1. Kiểm tra ở từng tầng lồng nhau

Chỉ kiểm tra các key root là chưa đủ:

```json
{
  "expectedVersion": 17,
  "purpose": "Mua thiết bị",
  "lines": [
    {
      "productId": "PRD-10",
      "quantity": 2,
      "approval": { "status": "APPROVED" }
    }
  ]
}
```

`lines` là trường đã biết nhưng phần tử chứa dữ liệu ngoài hợp đồng. Mỗi object và phần tử mảng phải được kiểm tra theo schema tương ứng.

Kiểm tra cả kiểu: `lines` phải là danh sách theo hợp đồng, mỗi phần tử phải là object dòng hàng. Không ép object, chuỗi hoặc giá trị null thành kiểu phù hợp mà không có quy ước rõ.

### 4.2. Tên trùng và cách giải mã tên

Một object có thể chứa hai thành viên cùng tên:

```json
{
  "quantity": 1,
  "quantity": 100
}
```

Nếu các tầng chọn giá trị khác nhau, validator có thể thấy 1 còn tầng thực hiện thấy 100. Với hợp đồng nghiêm, cần phát hiện trùng trước khi thông tin bị mất trong một map chỉ giữ một giá trị.

Tên cần được so sau bước giải mã cú pháp tương ứng. Một tên viết bằng escape không được tạo đường vòng để trở thành một thuộc tính có thẩm quyền mà tầng kiểm tra không nhận ra.

Không tùy ý trim, đổi chữ hoa thường hoặc chuẩn hóa mọi tên thành tên gần nhất. Tập alias và quy tắc khớp tên cần được khai báo, tránh việc sửa một lỗi chính tả thành thay đổi nghiệp vụ khác.

### 4.3. Giới hạn trước khi cấp phát không kiểm soát

Cần giới hạn kích thước request, độ sâu, số phần tử, số field và độ dài tên theo yêu cầu của endpoint.

Nếu chỉ đếm sau khi đã đọc toàn bộ một cấu trúc rất lớn vào bộ nhớ, giới hạn có thể đến quá muộn. Lớp đọc và các tầng phía trước cần phối hợp thực thi giới hạn thích hợp.

Từ chối trường ngoài hợp đồng giúp giữ đúng ngữ nghĩa, nhưng không tự thay thế các giới hạn tài nguyên.

## 5. Ví dụ Java: kiểm tra key trước khi bind sang command

Đoạn mã dùng các kiểu parser và path trừu tượng để thể hiện hợp đồng. Đây không phải API của một thư viện JSON cụ thể; phần triển khai phải bảo đảm những đặc tính được mô tả.

Giả sử `RawJsonObject` giữ danh sách thành viên với tên đã giải mã, chưa gộp thành map làm mất tên trùng.

```java
void requireExactFields(
        RawJsonObject object,
        Set<String> allowed,
        Set<String> required,
        InputPath path) {

    Set<String> seen = new HashSet<>();

    for (RawJsonMember member : object.members()) {
        String name = member.decodedName();

        if (!seen.add(name)) {
            throw new InvalidInput(
                    "DUPLICATE_FIELD", path.field(name));
        }

        if (!allowed.contains(name)) {
            throw new InvalidInput(
                    "UNKNOWN_FIELD", path.field(name));
        }
    }

    for (String requiredName : required) {
        if (!seen.contains(requiredName)) {
            throw new InvalidInput(
                    "MISSING_FIELD", path.field(requiredName));
        }
    }
}
```

Tập required phải là tập con của allowed trong định nghĩa hợp đồng. Lỗi cấu hình schema cần được nhận diện như lỗi phía hệ thống, không quy hết cho người gửi.

Hàm mới kiểm tra tên và sự hiện diện. Nó chưa xác nhận giá trị khác null, đúng kiểu, đúng phạm vi hoặc có quyền sử dụng tham chiếu.

### 5.1. Kiểm tra root và từng dòng hàng

```java
UpdateDraftCommand decodeUpdateDraft(
        String requestIdFromPath,
        byte[] rawBody) {

    RawJsonObject root = bodyReader.readRootObjectKeepingMembers(
            rawBody, requestLimits);

    Set<String> rootFields = Set.of(
            "expectedVersion", "purpose", "lines");

    requireExactFields(
            root, rootFields, rootFields, InputPath.root());

    RawJsonArray lines = root.require("lines").asArrayStrict();
    arrayRules.requireAllowedSize(lines.size());

    Set<String> lineFields = Set.of("productId", "quantity");

    for (int index = 0; index < lines.size(); index++) {
        RawJsonObject line = lines.get(index).asObjectStrict();

        requireExactFields(
                line, lineFields, lineFields,
                InputPath.root().field("lines").index(index));
    }

    UpdateDraftInput input = decoder.decodeExactTypes(root);
    inputRules.requireValid(input);

    return new UpdateDraftCommand(
            requestIdFromPath,
            input.expectedVersion(),
            input.purpose(),
            input.lines());
}
```

Các hợp đồng cần giữ:

- Reader kiểm tra cú pháp, giới hạn tài nguyên và giải mã tên đúng trước khi trả cấu trúc.
- Cấu trúc trung gian giữ được mọi thành viên cần thiết để phát hiện tên trùng.
- `asArrayStrict`, `asObjectStrict` và decoder không tự ép những kiểu ngoài hợp đồng thành đầu vào hợp lệ.
- `inputRules` kiểm tra null, chuỗi bắt buộc, số lượng hợp lệ, giới hạn số và các ràng buộc đầu vào cục bộ.
- `InputPath` được định dạng an toàn, có giới hạn khi đưa ra lỗi; không nối tên lạ nguyên dạng vào log hoặc thông báo.
- RequestId được lấy từ đường dẫn theo hợp đồng. Body không được ngầm thay đối tượng mà handler sẽ cập nhật.
- Entity không được tạo bằng cách chép tất cả thuộc tính của cấu trúc JSON.

Hợp đồng ví dụ không hỗ trợ alias hoặc vùng mở rộng. Nếu cần chúng, phải mở rộng schema và cách phát hiện xung đột có chủ đích, không chỉ bật một cơ chế bỏ qua lỗi tổng quát.

### 5.2. Vì sao kiểm tra sau khi tạo map có thể quá muộn?

Nếu parser chỉ giữ một giá trị khi gặp tên trùng, hàm kiểm tra map không còn thấy đủ dữ kiện để biết request ban đầu nhập nhằng.

Cần cấu hình hoặc chọn đường đọc có thể phát hiện tên trùng trước khi mất thông tin, hoặc giữ cấu trúc như mã giả. Không khẳng định một thư viện có hành vi này chỉ vì nó trả về một object tree; phải kiểm chứng đường cấu hình thực tế.

Tương tự, nếu một tầng đã bỏ trường ngoài hợp đồng trước khi validator chạy, validator không thể báo lại tên đã bị loại nếu không còn dữ kiện. Thứ tự parse, kiểm tra và bind là một phần của thiết kế.

## 6. Hợp đồng đầu vào không thay thế quyền và bất biến nghiệp vụ

Sau khi cấu trúc đã hợp lệ, handler vẫn cần:

1. Xác thực và xác định tenant có thẩm quyền.
2. Tải đúng đối tượng trong scope.
3. Kiểm tra quyền sửa bản nháp trên chính đối tượng đó.
4. Kiểm tra version, trạng thái và các điều kiện liên quan.
5. Xác minh sản phẩm, số lượng và các tham chiếu thuộc phạm vi được phép.
6. Tính giá, tổng tiền và dữ liệu dẫn xuất bằng nguồn có thẩm quyền.
7. Cập nhật tường minh những trường mà command được phép thay.
8. Lưu dữ liệu cùng audit, kết quả idempotency và outbox nếu áp dụng trong ranh giới transaction phù hợp.

Một `productId` đúng kiểu không chứng minh người gọi được sử dụng sản phẩm thuộc tenant khác. Một `quantity` là số nguyên dương vẫn có thể vượt hạn mức mua hoặc gây tràn trong cách tính nếu các ràng buộc liên quan không được bảo vệ.

### 6.1. Phân biệt nguồn của từng trường

| Dữ kiện | Nguồn trong ví dụ |
|---|---|
| purpose, productId, quantity | Đầu vào được phép, vẫn cần validation và kiểm tra tham chiếu |
| requestId | Đường dẫn đã được xử lý theo hợp đồng |
| tenant và danh tính thực | Ngữ cảnh xác thực, phân quyền có thẩm quyền |
| owner hiện tại, state, version hiện tại | Dữ liệu máy chủ đã tải |
| đơn giá và chính sách giảm giá | Nguồn giá cùng quy tắc nghiệp vụ |
| trạng thái sau hành động | Handler hoặc miền xác định theo lệnh |
| approvedBy và approvedAt | Chỉ được tạo bởi luồng quyết định có thẩm quyền |

Không nên coi tất cả dữ liệu sau khi deserialize là cùng mức tin cậy.

### 6.2. Không tạo thay đổi một phần trước khi phát hiện trường lạ

Nếu dòng đầu hợp lệ nhưng dòng cuối có `status` ngoài hợp đồng, lệnh nghiêm phải bị từ chối mà không giữ những thay đổi của dòng đầu.

Nên hoàn tất kiểm tra cấu trúc cần thiết trước tác dụng nghiệp vụ. Nếu nhập dữ liệu lớn phải đọc theo luồng, cần staging hoặc transaction theo hợp đồng để không biến việc kiểm tra muộn thành cập nhật dở dang.

Một response lỗi không đủ nếu cơ sở dữ liệu, kho tệp hoặc hệ thống ngoài đã bị tác động trước đó. Tác dụng không thể rollback cục bộ phải được điều phối ở đúng thời điểm.

### 6.3. Không nhận cả entity rồi khôi phục vài trường

Một cách dễ sai là bind toàn entity, sau đó gán lại owner hoặc status vì nghĩ những trường khác đã an toàn.

Cách đó có thể bỏ sót thuộc tính mới, quan hệ con hoặc một trường như hạn mức, revision hay người thụ hưởng. DTO riêng và cập nhật theo ý định làm phạm vi nhận rõ ràng hơn.

Ngay cả với DTO, không tự sao chép tất cả trường vào domain nếu DTO có cả dữ liệu chỉ để kiểm tra hoặc hiển thị. Mỗi trường cần vai trò cụ thể.

## 7. Alias, phân biệt tên và các kiểu cập nhật

### 7.1. Tên chính xác và alias khai báo

Nếu hợp đồng phân biệt tên chính xác, `quantity`, `Quantity` và `QUANTITY` không tự là một trường.

Nếu hỗ trợ alias để chuyển phiên bản, cần ánh xạ về một thuộc tính chuẩn và phát hiện trường hợp hai tên cùng xuất hiện. Chính sách nghiêm có thể từ chối ngay cả khi hai giá trị giống nhau để không tạo quy tắc chọn giá trị nhập nhằng.

Tên viết bằng escape cần được giải mã trước kiểm tra tên trùng. Việc kiểm tra một chuỗi JSON thô bằng tìm từ khóa không thay thế parser hiểu cấu trúc và cách giải mã.

Không dùng cơ chế đoán tên gần đúng để biến mọi field lạ thành field đã biết trong lệnh nhạy cảm.

### 7.2. Thiếu, null, rỗng và giá trị mặc định

Với lệnh cập nhật từng phần, cần xác định:

| Đầu vào | Câu hỏi hợp đồng phải trả lời |
|---|---|
| Không có trường | Giữ giá trị cũ hay thiếu dữ kiện bắt buộc? |
| Có trường với null | Xóa giá trị, giá trị không hợp lệ hay một ý nghĩa được định nghĩa khác? |
| Chuỗi rỗng | Giá trị hợp lệ, xóa nội dung hay bị chặn? |
| Danh sách rỗng | Xóa mọi dòng hay vi phạm yêu cầu tối thiểu? |
| Giá trị mặc định | Do người dùng chọn hay do server tự áp dụng? |

Không đánh đồng những trường hợp này bằng một phép kiểm tra `value != null`. Một thao tác có thể vô tình xóa dữ liệu hoặc giữ dữ liệu cũ trái ý định.

Quy tắc cụ thể còn phụ thuộc định dạng cập nhật mà API chọn. Cần kiểm tra đúng hợp đồng thay vì áp một mapper chung cho mọi endpoint.

### 7.3. Lệnh patch theo đường dẫn

Nếu endpoint nhận danh sách thao tác patch, các trường của thao tác và các đường dẫn đích đều cần validation.

Một path tới owner, tenant hoặc trạng thái không được cho phép chỉ vì payload có các key hợp lệ như `op`, `path` và `value`.

Cần xử lý path theo đúng cú pháp của định dạng, chuẩn hóa theo hợp đồng rồi kiểm tra thao tác, trường và kiểu giá trị được phép. Với thao tác có nguồn và đích, cả hai phía đều phải đáp ứng quyền và cấu trúc tương ứng.

Không dùng một phép kiểm tra tiền tố đơn giản để biến mọi đường dẫn dưới một object thành quyền sửa toàn bộ thuộc tính bên trong.

### 7.4. Query, form và các đường nhập khác

Cùng lệnh nghiệp vụ có thể được nhận qua JSON, query, form, import hoặc message. Mỗi đường cần chuyển về command có cùng giới hạn.

Tên query lặp, trường form trùng hoặc cột import ngoài hợp đồng cần chính sách rõ. Không bảo vệ JSON rồi để đường nhập khác ghi trực tiếp entity.

Một consumer không nên mặc định mọi key trong message đều là dữ kiện hệ thống có thẩm quyền chỉ vì message đến từ mạng nội bộ.

## 8. Tương thích phiên bản cần được thiết kế

Một client mới có thể gửi thêm field mà server cũ chưa biết. Từ chối có thể làm lộ vấn đề tương thích sớm; bỏ qua có thể khiến client tưởng một ý định đã được thực hiện dù server không hiểu.

Cần xác định:

- Phiên bản hợp đồng được chọn bằng cách nào.
- Trường nào được thêm và ở đâu.
- Server cũ xử lý phiên bản hoặc khả năng chưa hỗ trợ ra sao.
- Client có được gửi một field mới trước khi server hỗ trợ không.
- Có vùng mở rộng được khai báo hay cần một phiên bản command mới.

Không suy ra rằng thêm field luôn tương thích chỉ vì nó là optional trong một schema mới. Server cũ dùng chính sách nghiêm vẫn có thể từ chối tên đó theo đúng hợp đồng của nó.

### 8.1. Request nghiệp vụ và response có thể có chính sách khác nhau

Một client đọc response có thể được thiết kế để bỏ qua thuộc tính mới. Điều đó không tự chứng minh một server nên chấp nhận trường mới trong lệnh thay đổi trạng thái.

Hai phía có trách nhiệm khác nhau: response mô tả kết quả; command có thể tạo tác dụng, thay giá hoặc đi qua phê duyệt. Phải chọn chính sách cho từng chiều và từng loại giao diện.

Tương tự, một luồng telemetry dung nạp mở rộng không phải lý do để tắt kiểm tra trường lạ cho endpoint phê duyệt.

### 8.2. Message và callback từ hệ thống khác

Producer có thể phát thêm thuộc tính theo thỏa thuận. Consumer cần schema và version phù hợp, không mặc định mọi dữ liệu thêm đều là giá trị nghiệp vụ nên chép vào đối tượng.

Có thể tách envelope, phần dữ liệu được hiểu và vùng mở rộng. Các trường quyết định tenant, đối tượng, giao dịch hoặc kết quả vẫn cần kiểm chứng nguồn và mối liên hệ nghiệp vụ.

Một nguồn đã xác thực không đồng nghĩa mọi thuộc tính của nguồn đó có quyền quyết định owner, role hoặc trạng thái nội bộ của ứng dụng.

Nếu chọn dung nạp phần mở rộng, phần đó không được trở thành nhánh điều khiển ở một tầng khác mà schema không biết.

### 8.3. Không chữa tương thích bằng cấu hình rộng ngoài ý muốn

Một thay đổi bỏ qua field lạ ở mức toàn ứng dụng có thể ảnh hưởng nhiều endpoint, consumer và DTO khác.

Nên giới hạn theo hợp đồng cụ thể và kiểm chứng cấu hình hiệu lực trên đường chạy thật. Không giả định một annotation, bộ lọc hoặc cấu hình cục bộ sẽ có cùng tác dụng trong mọi cơ chế bind.

Khi nâng phiên bản framework hoặc thay mapper, cần xác nhận hành vi parse và unknown field vẫn phù hợp. Tên DTO và tài liệu mô tả không tự bảo đảm hành vi runtime.

## 9. Chuẩn hóa, fingerprint và idempotency

Thứ tự xử lý rất quan trọng với hợp đồng nghiêm:

```text
kiểm tra cú pháp và giới hạn
    → phát hiện trường ngoài hợp đồng, tên trùng và xung đột alias
    → kiểm tra kiểu, sự hiện diện và giá trị theo schema
    → dựng command có ngữ nghĩa rõ
    → tính fingerprint và xử lý idempotency
    → kiểm tra quyền, dữ liệu hiện tại và thực hiện nghiệp vụ
```

Đây là thứ tự cho phần diễn giải đầu vào. Xác thực người gọi, giới hạn request và bảo vệ quyền đọc kết quả vẫn phải được bố trí phù hợp ở ranh giới API.

### 9.1. Không xóa field lạ trước khi quyết định có chấp nhận không

Giả sử lần đầu:

```json
{
  "expectedVersion": 17,
  "purpose": "Thiết bị",
  "lines": [
    { "productId": "PRD-10", "quantity": 2 }
  ]
}
```

Lần sau dùng cùng idempotency key nhưng thêm:

```json
{
  "expectedVersion": 17,
  "purpose": "Thiết bị",
  "lines": [
    { "productId": "PRD-10", "quantity": 2 }
  ],
  "status": "APPROVED"
}
```

Với chính sách nghiêm, lần sau phải bị từ chối theo hợp đồng đầu vào. Không bỏ `status`, tính lại fingerprint trên phần còn lại rồi trả thành công như thể request mới vẫn hợp lệ.

Điều này không có nghĩa thực hiện lại lệnh đầu hoặc xóa kết quả cũ. Lệnh thành công trước vẫn giữ nguyên; đầu vào mới bị chặn.

### 9.2. Fingerprint phải phản ánh command thực sự

Fingerprint cần bao phủ các thành phần ảnh hưởng ngữ nghĩa, ví dụ:

- Loại action và đối tượng đích từ đường dẫn.
- Tenant hoặc phạm vi có thẩm quyền theo thiết kế scope của khóa.
- Version kỳ vọng và các precondition.
- Nội dung được nhận và các lựa chọn có tác dụng.
- Quan hệ đại diện hoặc đích phân phối nếu thuộc ý nghĩa lệnh.

Không chỉ băm vài trường rồi bỏ một tham số làm thay đổi hành động.

Việc chuẩn hóa thứ tự key hoặc cách biểu diễn có thể phù hợp khi ngữ nghĩa thực sự không đổi. Nhưng thiếu và null, danh sách có thứ tự và tập không thứ tự, hoặc số theo các kiểu được chấp nhận có thể mang nghĩa khác nhau. Không chuẩn hóa chúng thành một cách tùy ý.

Xung đột alias và tên trùng cần được xử lý trước khi tính một biểu diễn chuẩn, nếu không thao tác chuẩn hóa có thể che mất sự nhập nhằng.

### 9.3. Trường bị bỏ qua trong hợp đồng dung nạp

Nếu một giao diện được thiết kế để bỏ qua field ngoài hợp đồng, cần định nghĩa fingerprint theo dữ liệu thô hay command có hiệu lực.

Hai cách có thể cho kết quả khác nhau khi client thêm một trường bị bỏ qua. Hợp đồng phải nhất quán và bảo đảm phần bị bỏ qua thật sự không tác động qua log, metadata, mapper hoặc các tầng khác.

Không áp dụng một quy tắc fingerprint chung để hợp thức hóa hành vi bỏ qua ở những endpoint đã cam kết nghiêm.

### 9.4. Chữ ký payload và chuẩn hóa ứng dụng

Nếu có chữ ký hoặc cơ chế xác minh nội dung từ producer, bước xác minh phải tuân theo hợp đồng ký: dữ liệu thô hoặc biểu diễn chuẩn mà giao thức quy định.

Không xóa field lạ rồi xác minh một payload đã thay đổi như thể đó là thông điệp nguồn đã gửi. Ngược lại, chữ ký hợp lệ cũng không thay thế validation và quyền dùng dữ kiện trong nghiệp vụ.

Chỉ giữ và truy cập dữ liệu thô theo nhu cầu cùng chính sách bảo vệ; không ghi nguyên request vào log chỉ vì cần chẩn đoán chữ ký.

## 10. Phản hồi lỗi và dấu vết an toàn

Một phản hồi có thể là:

```json
{
  "code": "INVALID_COMMAND_BODY",
  "errors": [
    {
      "code": "UNKNOWN_FIELD",
      "path": "$.lines[0].unitPrice"
    }
  ],
  "correlationId": "CORR-410"
}
```

Mã HTTP phụ thuộc hợp đồng API. Điều quan trọng là lỗi thể hiện đầu vào chưa được chấp nhận và không khiến client hiểu phần còn lại đã được thực hiện.

### 10.1. Đường dẫn lỗi cần đủ dùng và có giới hạn

Có thể chỉ ra đường dẫn field thay vì lặp giá trị. Tên do người dùng kiểm soát có thể dài, chứa ký tự điều khiển hoặc nội dung gây hiểu nhầm; formatter cần escape và giới hạn phù hợp.

Không liệt kê mọi thuộc tính nội bộ của entity để gợi ý các field được phép. Thông tin phản hồi nên dựa trên hợp đồng công khai của endpoint.

Số lỗi trả về cũng cần giới hạn. Một payload cố tình tạo nhiều lỗi không nên làm phản hồi hoặc log tăng không kiểm soát.

### 10.2. Không ghi nguyên phần không hiểu vào log

Field lạ có thể chứa token, dữ liệu cá nhân hoặc một payload rất lớn. Thu gom mọi giá trị ngoài schema vào log có thể tạo một đường rò rỉ mới.

Có thể ghi mã lỗi, endpoint, phiên bản hợp đồng, đường dẫn đã xử lý an toàn, producer có thẩm quyền nếu biết và correlationId. Dữ liệu điều tra chi tiết cần chính sách riêng.

Nhiều lần thêm owner, trạng thái hoặc thuộc tính quyền có thể là tín hiệu lạm dụng. Một field viết sai hoặc client cũ cũng có thể là lỗi tích hợp. Cần xét chuỗi hành vi và ngữ cảnh thay vì coi mọi lỗi unknown field là tấn công.

### 10.3. Không đổi lỗi cấu trúc thành thực hiện một phần

Một khối bắt lỗi không nên làm như sau:

```text
validator báo trường lạ
    → ghi warning
    → tiếp tục handler với phần dữ liệu còn lại
```

Nếu hợp đồng nghiêm, đây là thay đổi ngữ nghĩa. Lệnh phải kết thúc trước tác dụng nghiệp vụ hoặc rollback theo ranh giới đã xác định.

Dấu vết từ chối có thể còn tồn tại, nhưng không có audit giả rằng đơn đã được sửa thành công.

## 11. Duy trì hợp đồng khi mô hình thay đổi

Mỗi field đầu vào nên được phân loại theo mục đích:

| Loại | Ví dụ | Cách xử lý |
|---|---|---|
| Nội dung người dùng được nhập | purpose, quantity | Kiểm tra cấu trúc, giá trị, quyền và ngữ cảnh |
| Precondition | expectedVersion | So với nguồn hiện tại; không dùng làm nguồn chân lý |
| Dữ liệu máy chủ sinh | trạng thái quyết định, thời điểm phê duyệt | Không nhận như quyền tự ghi của client |
| Dữ liệu dẫn xuất | tổng tiền theo chính sách | Tính hoặc xác minh theo nguồn có thẩm quyền |
| Tham chiếu | productId, attachmentId | Kiểm tra tồn tại, tenant và quyền dùng |
| Phần mở rộng | metadata đã khai báo | Cô lập và giới hạn theo schema riêng |

Khi thêm trường vào DTO, cần xem nó thuộc loại nào và endpoint nào được phép nhận. Không chỉ thêm thuộc tính để đáp ứng một response rồi vô tình mở input cùng tên.

Các schema, decoder và mapper cần thống nhất. Một schema từ chối nhưng một đường bind khác vẫn nhận entity là một đường vòng có thể bị bỏ sót.

### 11.1. Các cách triển khai dễ sai

| Cách làm | Rủi ro |
|---|---|
| Nhận entity trực tiếp | Mở các thuộc tính không thuộc lệnh |
| Chỉ kiểm tra key root | Bỏ sót trường lạ trong object con hoặc mảng |
| Dùng blacklist vài field nhạy cảm | Field mới có thể được nhận ngoài ý muốn |
| Tạo map trước rồi kiểm tra tên trùng | Thông tin trùng có thể đã mất |
| Dùng cơ chế sửa tên gần đúng | Ánh xạ sang một ý định không được gửi rõ |
| Lọc hoặc xóa dữ liệu trước validation nghiêm | Che mất trường thừa và xung đột |
| Thu nhận vào extras rồi merge vào domain | Khôi phục đường gán hàng loạt qua cửa sau |
| Chỉ có validation giá trị trên DTO | Field lạ có thể đã bị bỏ trước khi validator nhìn thấy |
| Bắt lỗi rồi tiếp tục xử lý | Lệnh không hợp lệ vẫn tạo tác dụng |
| Tắt kiểm tra toàn ứng dụng để hỗ trợ một client | Đổi hành vi nhiều hợp đồng ngoài phạm vi cần thiết |

Các kiểm thử hợp đồng nên chạy qua đường nhận request thực, không chỉ gọi hàm kiểm tra DTO đã được tạo sẵn. Cần nhìn được parser, alias, cấu hình bind và hành vi lỗi đang có hiệu lực.

## 12. Kiểm thử trường ngoài hợp đồng và sự nhập nhằng

### 12.1. Ma trận tối thiểu

| Tình huống | Kết quả cần kiểm chứng trong hợp đồng nghiêm |
|---|---|
| Root có field viết sai | Từ chối, không âm thầm thay bằng giá trị mặc định |
| Root có status hoặc owner không thuộc lệnh | Không ghi vào entity |
| Phần tử dòng hàng có unitPrice ngoài schema | Từ chối dù root hợp lệ |
| Field lạ nằm ở phần tử cuối của mảng | Không giữ cập nhật của phần tử trước |
| Field lạ có giá trị null hoặc bằng giá trị hiện tại | Vẫn xử lý theo hợp đồng trường, không vì giá trị có vẻ vô hại mà cho qua |
| Tên trùng tại root | Phát hiện trước khi mất thông tin |
| Tên trùng trong object con | Không chỉ kiểm tra trùng ở root |
| Hai cách viết escape giải mã thành cùng tên | Không tạo hai cách diễn giải khác nhau |
| Hai alias cùng trỏ một thuộc tính | Áp dụng quy tắc xung đột rõ, không tùy tầng chọn |
| Khác chữ hoa thường ngoài alias được hỗ trợ | Không tự đoán tên field |
| Trường bắt buộc vắng hoặc có null | Phân biệt đúng hai trường hợp |
| quantity sai kiểu, vượt phạm vi hoặc không hợp lệ | Không ép kiểu rồi tiếp tục ngoài hợp đồng |
| productId đúng cấu trúc nhưng ngoài tenant | Kiểm tra quyền và tham chiếu vẫn chặn |
| Thêm field mới vào entity nhưng không đổi command | Field đó không tự được nhận từ API |
| Patch có op hợp lệ nhưng path tới owner | Không vượt qua quyền theo trường |
| Field được khai báo trong metadata mở rộng | Chỉ có tác dụng trong vùng được định nghĩa, không ghi đè domain |
| Cùng key của lệnh cũ nhưng thêm status lạ | Từ chối đầu vào mới, không tạo thêm tác dụng và không xóa kết quả trước |
| Client mới gửi phiên bản chưa được hỗ trợ | Phản hồi đúng hợp đồng tương thích, không giả vờ đã hiểu ý định |
| Query hoặc form có tên lạ, tên trùng | Cùng lệnh không có đường bind rộng hơn ngoài ý muốn |
| Payload vượt độ sâu hoặc kích thước | Bị giới hạn trước khi gây tiêu tốn không kiểm soát |

Cần thêm các trường hợp producer và consumer có cấu hình riêng nếu cùng nghiệp vụ đi qua nhiều kênh.

### 12.2. Gửi dữ liệu thô khi kiểm thử tên trùng

Không chỉ tạo một map rồi serialize để test duplicate field, vì map có thể không giữ được hai thành viên cùng tên.

Ví dụ payload thô để kiểm tra:

```json
{
  "expectedVersion": 17,
  "purpose": "Giá trị thứ nhất",
  "\u0070urpose": "Giá trị thứ hai",
  "lines": [
    { "productId": "PRD-10", "quantity": 2 }
  ]
}
```

Hai tên purpose phải được hiểu theo kết quả giải mã cú pháp trước khi xác định trùng. Test cần đi qua parser và binder thực tế.

Cũng cần kiểm tra trường hợp một tầng nhận map, một tầng nhận DTO và một consumer nhận message để phát hiện khác biệt cấu hình. Không suy ra tất cả đều nghiêm chỉ vì một helper trả lỗi đúng.

### 12.3. Kiểm tra không có thay đổi nghiệp vụ

Sau khi từ chối vì field lạ hoặc cấu trúc nhập nhằng:

```text
nội dung, giá và tổng tiền không bị sửa bởi lệnh thất bại
owner, tenant và trạng thái không bị thay
version và revision không tăng dở dang
không có dòng hàng được ghi một phần
không có quyết định phê duyệt hoặc execution mới
không tạo outbox báo đã chấp nhận lệnh
không gọi hệ thống ngoài từ nhánh bị chặn
không ghi kết quả idempotency như một lần thành công mới
không ghi audit nghiệp vụ thành công giả
```

Bộ đếm bảo vệ, log từ chối hoặc telemetry có thể thay đổi theo chính sách. Chúng cần được phân biệt với dữ liệu nghiệp vụ đã được chấp nhận.

Với lệnh thành công đã có từ trước, một payload mới bị từ chối không được làm mất hoặc sửa kết quả cũ.

### 12.4. Kiểm thử thông báo lỗi

Gửi tên field có ký tự điều khiển, tên dài và nhiều lỗi cùng lúc để kiểm tra:

- Đường dẫn lỗi được định dạng an toàn.
- Không lặp giá trị nhạy cảm.
- Không lộ thuộc tính nội bộ ngoài hợp đồng công khai.
- Kích thước và số lỗi được giới hạn.
- Log không bị tách thành các bản ghi giả.
- CorrelationId và mã lỗi đủ để điều tra theo quyền truy cập.

Không dùng dữ liệu bí mật thật trong fixture chỉ để kiểm tra cơ chế không ghi log.

### 12.5. Kiểm thử hồi quy của hợp đồng

Khi thêm field hoặc thay mapper, cần xác nhận:

1. Field mới chỉ được nhận ở những command đã cho phép.
2. Những field máy chủ quản lý vẫn bị chặn.
3. Object con và phần tử mảng vẫn có schema đúng.
4. Alias cũ không tạo xung đột với tên mới.
5. Quy tắc thiếu, null, rỗng và mặc định không đổi ngoài ý định.
6. Fingerprint giữ đúng ngữ nghĩa lệnh sau thay đổi.
7. Endpoint, import và consumer không có đường cập nhật entity rộng hơn.
8. Chính sách tương thích được giữ khi các phiên bản khác nhau cùng hoạt động.

Các ca này kiểm tra ý nghĩa và ranh giới dữ liệu, thay vì chỉ kiểm tra một tùy chọn cấu hình mang tên “strict” đã được bật.

## 13. Bài tập áp dụng

Thiết kế đầu vào sửa đơn mua hàng nháp, chỉ nhận mục đích, dòng hàng và version kỳ vọng.

1. Liệt kê trường được nhận ở root, dòng hàng và mọi object con.
2. Phân loại owner, tenant, status, đơn giá, tổng tiền và thông tin phê duyệt theo nguồn có thẩm quyền.
3. Chọn chính sách với field lạ, field chỉ đọc, tên trùng, alias và null.
4. Vẽ thứ tự đọc payload, kiểm tra cấu trúc, bind, fingerprint, phân quyền và ghi dữ liệu.
5. Thiết kế lỗi đủ rõ mà không lộ payload hoặc thuộc tính nội bộ.
6. Mô tả cách thay đổi schema khi client mới cần một trường bổ sung.
7. Chỉ ra cách một vùng metadata có thể tồn tại mà không trở thành đường gán hàng loạt.
8. Viết ca trường lạ ở dòng cuối, tên trùng sau giải mã và replay có thêm status.
9. Xác định dữ liệu và tác dụng nào phải vắng mặt sau mỗi lần từ chối.

Một hợp đồng đầu vào an toàn cần cho biết chính xác người gọi được diễn đạt ý định gì, bằng những trường nào và theo cách hiểu nào. Những dữ kiện quyết định quyền, trạng thái và giá trị nghiệp vụ phải tiếp tục có nguồn cùng kiểm soát phù hợp, kể cả sau khi payload đã vượt qua kiểm tra cấu trúc.

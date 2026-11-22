# PATCH và điều kiện dùng định dạng bản vá

Trong module **INTEGRATION_API_REST**, thiết kế phương thức HTTP luôn đi cùng resource, URI và hợp đồng dữ liệu. Bài này tập trung vào một tình huống: người dùng chỉ sửa một phần hồ sơ khách hàng, trong khi hệ thống vẫn phải bảo vệ các trường còn lại, quyền chỉnh sửa và dữ liệu vừa được người khác cập nhật.

Sau bài học, bạn có thể chọn giữa JSON Merge Patch và JSON Patch, mô tả chính xác ý nghĩa của trường vắng mặt và `null`, thiết kế PATCH có điều kiện, và tổ chức việc áp dụng bản vá trong Java/Spring. Những ví dụ dưới đây là hợp đồng minh hoạ cho một API quản lý khách hàng; các giới hạn nghiệp vụ được nêu rõ để có thể thay bằng quy tắc của hệ thống thực tế.

## 1. PATCH gửi yêu cầu thay đổi như thế nào?

`PATCH /customers/42` yêu cầu áp dụng một bản vá lên resource khách hàng số 42. Body là tài liệu mô tả thay đổi; **định dạng bản vá quyết định cách diễn giải body**. PUT mang biểu diễn thay thế, còn PATCH mang chỉ dẫn sửa đổi. PATCH không mặc nhiên an toàn hay idempotent; server phải áp dụng bản vá nguyên tử, tránh trạng thái chỉ hoàn tất một phần. Các đặc điểm này được quy định trong [RFC 5789, mục 2](https://www.rfc-editor.org/rfc/rfc5789.html#section-2).

Giả sử GET trả về:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "customer-42-v8"

{
  "id": 42,
  "displayName": "An",
  "phone": "0900000042",
  "address": {
    "city": "Huế",
    "postalCode": "530000"
  },
  "tags": ["newsletter", "priority"]
}
```

Người dùng chỉ muốn đổi tên hiển thị. Với hợp đồng JSON Merge Patch, request có thể là:

```http
PATCH /customers/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json
Accept: application/json
If-Match: "customer-42-v8"

{
  "displayName": "An Nguyễn"
}
```

Ở đây URI xác định khách hàng; `Content-Type` xác định cách hiểu bản vá; `Accept` nói về định dạng phản hồi; `If-Match` gắn việc sửa với phiên bản đã đọc.

Không thể chỉ ghi “nhận JSON” trong hợp đồng rồi mong mọi client hiểu giống nhau. Một client có thể cho rằng `null` là xoá, client khác muốn lưu giá trị null; một client muốn thay cả mảng, client khác muốn nối thêm phần tử. Những khác biệt này phải được giải quyết ngay khi chọn định dạng.

### Phân biệt nhu cầu cập nhật với thao tác nghiệp vụ

| Nhu cầu của màn hình | Thiết kế minh hoạ | Lý do lựa chọn |
| --- | --- | --- |
| Thay toàn bộ cấu hình thông báo do người dùng quản lý | `PUT /customers/42/notification-preferences` | Client sở hữu biểu diễn đầy đủ của cấu hình |
| Sửa tên và địa chỉ đang hiển thị | `PATCH /customers/42` | Các thay đổi có thể diễn tả trực tiếp trên dữ liệu hồ sơ |
| Thêm một đăng ký nhận tin có danh tính riêng | `POST /customers/42/subscriptions` | Tạo một resource con có vòng đời riêng |
| Yêu cầu hoàn tiền cho một thanh toán | `POST /payments/81/refund-requests` | Có kiểm tra, phê duyệt và trạng thái xử lý riêng |

Đây là lựa chọn mô hình của ví dụ, không phải quy tắc ép mọi hành động phải dùng cùng một URI. Nếu “đổi một trường” thực chất khởi động thanh toán, phê duyệt hoặc phát hành tài liệu, hãy thiết kế theo ý nghĩa nghiệp vụ thay vì cho client sửa tuỳ ý trạng thái nội bộ.

## 2. Chốt hợp đồng trước khi chọn thư viện

Với API hồ sơ trong bài, nhóm phát triển thống nhất:

- Chỉ nhận PATCH cho khách hàng đã tồn tại; không tạo mới bằng PATCH.
- `id`, chủ sở hữu và quyền hệ thống do server quản lý.
- Người dùng được sửa `displayName`, `phone`, `address` và `tags` trong phạm vi được cấp quyền.
- `displayName` là chuỗi không trắng, tối đa 100 ký tự; không được xoá.
- `phone` là tuỳ chọn; thao tác xoá làm thuộc tính này vắng mặt trong biểu diễn trả về.
- Khi có `address`, địa chỉ phải có `city` hợp lệ; thay đổi thành phố có thể kéo theo kiểm tra mã bưu chính.
- Mỗi cập nhật cần phiên bản đã đọc. Bản vá sai hoặc xung đột không được làm thay đổi dữ liệu.
- Phản hồi thành công trả biểu diễn đã lưu cùng ETag mới.

Việc thống nhất các điểm này giúp tách hai câu hỏi: “bản vá có hợp lệ theo định dạng không?” và “trạng thái sau khi vá có được nghiệp vụ chấp nhận không?”. Một thư viện có thể trả về cây JSON hoàn toàn hợp lệ nhưng cây đó vẫn thiếu tên bắt buộc hoặc chứa trường vượt quyền.

## 3. JSON Merge Patch: diễn tả giá trị muốn thay đổi

Media type của JSON Merge Patch là `application/merge-patch+json`. Với object, thuộc tính vắng mặt được giữ lại; giá trị `null` yêu cầu xoá thuộc tính; object được xử lý đệ quy. Mảng được thay cả giá trị. Bản vá không phải object thay toàn bộ giá trị đích, nên chuẩn không giới hạn bản vá ở object. Xem [RFC 7396, mục 2](https://www.rfc-editor.org/rfc/rfc7396.html#section-2).

### 3.1. Ví dụ cập nhật nhiều trường

Áp dụng lên hồ sơ ở phần 1:

```json
{
  "displayName": "An Nguyễn",
  "phone": null,
  "address": {
    "city": "Đà Nẵng"
  }
}
```

Kết quả ứng viên trước khi kiểm tra nghiệp vụ:

```json
{
  "id": 42,
  "displayName": "An Nguyễn",
  "address": {
    "city": "Đà Nẵng",
    "postalCode": "530000"
  },
  "tags": ["newsletter", "priority"]
}
```

Ví dụ cho thấy một vấn đề quan trọng của ứng dụng: mã bưu chính cũ vẫn còn. Nếu mã này không phù hợp thành phố mới, server cần từ chối và yêu cầu người dùng gửi thêm thông tin. Không nên tự coi “merge thành công” là “địa chỉ hợp lệ”.

### 3.2. Bảng phân biệt trường vắng mặt, null và rỗng

Trong hợp đồng hồ sơ đang xét:

| Body gửi tới server | Kết quả ứng viên | Kiểm tra tiếp theo |
| --- | --- | --- |
| `{}` | Hồ sơ hiện tại được giữ nguyên | API phải quy định phản hồi khi không có thay đổi |
| `{"phone": null}` | Bỏ thuộc tính `phone` | Cho phép vì điện thoại là tuỳ chọn |
| `{"phone": ""}` | Điện thoại thành chuỗi rỗng | Từ chối nếu chuỗi rỗng không phải số điện thoại hợp lệ |
| `{"displayName": null}` | Tên hiển thị bị bỏ | Từ chối vì tên bắt buộc |
| `{"tags": []}` | Danh sách nhãn trở thành rỗng | Cho phép nếu người dùng có quyền xoá các nhãn |
| `{"address": {}}` | Địa chỉ object hiện tại được giữ nguyên | Không coi đây là lệnh xoá địa chỉ |
| `{"address": null}` | Địa chỉ bị bỏ | Chấp nhận hay từ chối theo quy tắc hồ sơ |

Không chuyển ngay request vào DTO mà cả “không gửi trường” và “gửi null” đều biến thành cùng một giá trị Java `null`. Sau bước đó, service không còn đủ thông tin để quyết định giữ nguyên hay xoá.

### 3.3. Khi nào nên chọn Merge Patch?

Một màn hình sửa hồ sơ nhỏ phù hợp với Merge Patch khi người dùng chỉnh các giá trị scalar hoặc object, ít phải thao tác từng phần tử mảng. Nhóm client có thể dựng body từ những trường người dùng thực sự đã sửa.

Nếu miền dữ liệu cần phân biệt rõ “thuộc tính tồn tại với giá trị JSON null” và “thuộc tính không tồn tại”, nên cân nhắc JSON Patch. Với danh sách lớn, việc gửi lại toàn bộ `tags` cũng gây khó cho client và làm tăng nguy cơ ghi đè thay đổi của người khác.

API hồ sơ có thể giới hạn root của bản vá phải là object để bảo vệ cấu trúc hồ sơ. Khi đó request body `null`, một mảng hoặc một chuỗi bị từ chối theo hợp đồng ứng dụng, dù chúng là giá trị JSON và có ngữ nghĩa trong chuẩn Merge Patch.

## 4. JSON Patch: diễn tả các thao tác cụ thể

JSON Patch dùng media type `application/json-patch+json`. Body là mảng thao tác được thực hiện tuần tự; thao tác sau nhìn thấy kết quả thao tác trước. Sáu thao tác chuẩn gồm `add`, `remove`, `replace`, `move`, `copy`, `test`. Lỗi ở một thao tác làm bản vá không hoàn tất thành công. Xem [RFC 6902, mục 3–5](https://www.rfc-editor.org/rfc/rfc6902.html#section-3).

Ví dụ trên một bản hồ sơ vẫn còn số điện thoại:

```http
PATCH /customers/42 HTTP/1.1
Host: api.example.test
Content-Type: application/json-patch+json
If-Match: "customer-42-v8"

[
  { "op": "test", "path": "/displayName", "value": "An" },
  { "op": "replace", "path": "/displayName", "value": "An Nguyễn" },
  { "op": "remove", "path": "/phone" },
  { "op": "add", "path": "/tags/-", "value": "beta-user" }
]
```

| Thao tác | Ý nghĩa cần nhớ |
| --- | --- |
| `add` | Thêm thành viên object hoặc chèn phần tử mảng; thành viên object có sẵn có thể bị thay |
| `remove` | Xoá giá trị tại đường dẫn đang tồn tại |
| `replace` | Thay giá trị tại đường dẫn đang tồn tại |
| `move` | Lấy giá trị từ `from`, xoá ở nguồn và thêm tại `path` |
| `copy` | Sao chép giá trị từ `from` tới `path` |
| `test` | So sánh giá trị tại `path` với `value`; không khớp thì thất bại |

Khi thay một thuộc tính đang tồn tại bằng `{"op":"replace","path":"/phone","value":null}`, kết quả là giá trị null. Điều này khác thao tác `remove`.

### 4.1. Đọc đường dẫn đúng cách

`path` và `from` dùng JSON Pointer: `/address/city` trỏ tới thành phố; `/tags/0` trỏ tới phần tử đầu tiên. Ký tự `~` trong tên thuộc tính được mã hoá thành `~0`, còn `/` thành `~1`. Ví dụ tên thuộc tính `a/b` được trỏ bằng `/a~1b`. Chuỗi pointer rỗng trỏ tới toàn bộ tài liệu. Xem [RFC 6901, mục 3–4](https://www.rfc-editor.org/rfc/rfc6901.html#section-3).

Trong JSON Patch, `/tags/-` được dùng làm đích của `add` để thêm vào cuối mảng. Khi xoá phần tử thứ 0, các chỉ số phía sau dịch chuyển. Do đó danh sách thao tác của client phải được đánh giá theo thứ tự, không thể tự sắp xếp lại “cho dễ tối ưu”.

### 4.2. Khi nào nên chọn JSON Patch?

Một trình biên tập tài liệu cần xoá, chèn hoặc di chuyển từng mục có thể hưởng lợi từ JSON Patch. Một client đồng bộ thay đổi cũng có thể biểu diễn rõ thao tác thay vì gửi lại toàn bộ cấu trúc.

Đổi lại, client phải hiểu đường dẫn và trạng thái nền. Nếu `/tags/1` từng là nhãn `priority` nhưng người khác vừa xoá phần tử đầu, chỉ số 1 có thể chỉ sang nhãn khác. Với phần tử có danh tính nghiệp vụ, API như `/customers/42/subscriptions/{subscriptionId}` thường giúp client diễn đạt ý định ổn định hơn.

`test` phù hợp khi client muốn nêu điều kiện trên một trường. Nó không tự bảo vệ các trường khác khỏi cập nhật đồng thời; việc kiểm tra và ghi dữ liệu vẫn cần nằm trong một cơ chế kiểm soát cạnh tranh.

## 5. Chọn định dạng theo dữ liệu và client

| Câu hỏi thiết kế | Merge Patch | JSON Patch |
| --- | --- | --- |
| Form chỉ sửa một vài giá trị | Body dễ dựng từ các trường đã sửa | Cần chuyển thay đổi thành danh sách thao tác |
| Muốn lưu JSON null như một giá trị | Không biểu đạt trực tiếp việc gán null cho thành viên object | Có thể dùng `add` hoặc `replace` với `value: null` |
| Muốn sửa từng phần tử mảng | Gửi lại cả mảng | Có thao tác theo chỉ số |
| Muốn nêu điều kiện trên giá trị cũ | Xử lý qua điều kiện HTTP hoặc quy tắc ứng dụng | Có thêm thao tác `test` |
| Client ít hiểu cấu trúc nội bộ | Có thể cung cấp schema cập nhật nhỏ, rõ | Cần tài liệu và giới hạn đường dẫn cẩn thận |

Đối với hồ sơ trong bài, có thể bắt đầu bằng **chỉ Merge Patch** và thêm JSON Patch khi có nhu cầu thao tác đủ cụ thể. Hỗ trợ đồng thời hai định dạng làm tăng số hợp đồng, kiểm tra quyền và tình huống kiểm thử cần duy trì.

Nếu API định nghĩa một body cập nhật riêng dưới `application/json`, phải mô tả chính xác các quy tắc của body đó. Không gọi nó là JSON Merge Patch nếu cách xử lý null hoặc mảng khác chuẩn.

### Công bố định dạng hỗ trợ

API có thể trả lời OPTIONS như sau:

```http
HTTP/1.1 204 No Content
Allow: GET, HEAD, PATCH, OPTIONS
Accept-Patch: application/merge-patch+json, application/json-patch+json
```

`Allow` công bố phương thức, còn `Accept-Patch` công bố media type bản vá mà resource chấp nhận. Khi từ chối định dạng bằng 415, phản hồi có thể kèm `Accept-Patch` để client biết lựa chọn phù hợp. Xem [RFC 5789, mục 2.2 và 3](https://www.rfc-editor.org/rfc/rfc5789.html#section-3).

Danh sách trên chỉ phù hợp khi server thực sự triển khai cả hai định dạng. Nếu sản phẩm mới nhận Merge Patch thì chỉ quảng bá media type tương ứng. Với trình duyệt gọi khác origin, cấu hình CORS cũng phải cho phép PATCH cùng các request header cần dùng, và expose `ETag` nếu JavaScript cần đọc header này.

## 6. Ngăn ghi đè bằng If-Match và lưu có điều kiện

Giả sử hai người cùng đọc khách hàng ở phiên bản v8:

1. Người A sửa số điện thoại, server lưu thành v9.
2. Người B đổi thành phố dựa trên dữ liệu v8.
3. Nếu B gửi lại cả địa chỉ cũ mà server chấp nhận vô điều kiện, một thay đổi mới có thể bị ghi đè.

`If-Match` dùng phép so sánh ETag mạnh. Validator yếu như `W/"customer-42-v8"` không thoả phép so sánh mạnh; `If-Match: *` chỉ kiểm tra tồn tại, không khóa một phiên bản cụ thể. Khi điều kiện phiên bản không còn đúng, server thường trả `412 Precondition Failed`. Xem [RFC 9110, mục 13.1.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1).

Với hợp đồng của bài, B gửi:

```http
If-Match: "customer-42-v8"
```

Server đang ở v9 nên từ chối. Client đọc lại dữ liệu, hiển thị khác biệt nếu cần, rồi dựng một bản vá mới dựa trên phiên bản hiện tại. Không tự thay header bằng ETag mới và gửi lại bản vá cũ mà chưa xem xét ý định người dùng.

Nếu API bắt buộc request có điều kiện, thiếu điều kiện có thể nhận `428 Precondition Required`, được định nghĩa trong [RFC 6585, mục 3](https://www.rfc-editor.org/rfc/rfc6585.html#section-3). Đây là chính sách API được công bố trước, không phải yêu cầu bắt buộc cho mọi endpoint PATCH.

### 6.1. Chỉ so ETag ở controller là chưa đủ

Hai request có thể đồng thời vượt qua phép so sánh v8 ở tầng Java trước khi request nào ghi xuống cơ sở dữ liệu. Cần bảo vệ cả thời điểm commit:

```sql
UPDATE customers
SET profile_json = :newProfile,
    version = version + 1
WHERE id = :customerId
  AND version = :expectedVersion;
```

Ví dụ này giả định mọi thay đổi của hồ sơ đều tăng cùng cột `version`. Nếu update ảnh hưởng 0 dòng do phiên bản đã đổi, service không được báo thành công. Sau khi phân loại nguyên nhân, service trả lỗi phù hợp với điều kiện request; với ETag cũ của ví dụ là 412.

Có thể dùng optimistic locking của tầng lưu trữ hoặc khoá phù hợp. Dù chọn cách nào, phép kiểm tra phiên bản và phép ghi phải cùng bảo vệ một trạng thái resource. Một transaction chỉ bao quanh câu lệnh `save` trong khi đọc và kiểm tra ở ngoài vẫn có thể để lọt cập nhật cạnh tranh.

ETag minh hoạ trong bài chỉ hợp lệ như validator mạnh nếu server bảo đảm phiên bản thay đổi mỗi khi biểu diễn được chọn thay đổi. Các biến thể biểu diễn hoặc cơ chế tính ETag khác cần được thiết kế nhất quán.

## 7. Nguyên tử, idempotency và retry là ba vấn đề riêng

Giả sử bản vá gồm đổi tên, xoá điện thoại và thêm nhãn. Nếu thao tác cuối thất bại, tên và điện thoại cũng phải giữ trạng thái trước request. Cách tổ chức phù hợp cho ví dụ:

```text
Xác thực và kiểm tra quyền truy cập resource
  -> Kiểm tra media type và cấu trúc bản vá
  -> Đọc trạng thái + phiên bản
  -> Kiểm tra điều kiện If-Match
  -> Kiểm tra quyền với các trường/đường dẫn liên quan
  -> Áp dụng toàn bộ bản vá lên bản sao
  -> Kiểm tra schema và nghiệp vụ trên kết quả cuối
  -> Lưu có điều kiện trong transaction
  -> Commit rồi trả biểu diễn + ETag
```

Không sửa trực tiếp entity đang được ORM quản lý trước khi bản vá được chấp nhận. Một exception bị bắt sai hoặc flush ngoài dự kiến có thể khiến một phần dữ liệu bị lưu.

Về retry, hãy xem ý nghĩa của thao tác:

- Gán `displayName` thành cùng một giá trị thường giữ nguyên trạng thái khi áp dụng lặp lại, nếu không có quy tắc nghiệp vụ làm phát sinh thay đổi khác.
- `add` một nhãn vào `/tags/-` có thể nối cùng nhãn nhiều lần nếu request được áp dụng nhiều lần.
- Gửi lại request với ETag cũ sau khi lần đầu đã commit sẽ thường bị 412 theo chính sách của ví dụ. Lỗi đó không cho client biết chắc lần đầu đã thành công hay một người khác đã cập nhật.

Nếu client mất kết nối sau khi gửi, nó cần đối chiếu trạng thái hiện tại hoặc dùng cơ chế theo dõi request mà API thiết kế. Một hợp đồng `Idempotency-Key` bổ sung, nếu có, phải quy định phạm vi key, thời gian lưu, cách phát hiện cùng key khác payload và cách phát lại kết quả. Chỉ thêm tên header vào tài liệu chưa tạo ra khả năng chống thực thi lặp.

Nếu đổi hồ sơ kéo theo gửi sự kiện, ví dụ có thể ghi sự kiện vào outbox trong cùng transaction. Bộ phát sự kiện và bên nhận vẫn cần xử lý trùng. Transaction cơ sở dữ liệu không tự biến việc gửi email hoặc gọi hệ thống khác thành thao tác nguyên tử.

## 8. Kiểm tra quyền trên từng thay đổi

Có quyền PATCH hồ sơ không có nghĩa là được sửa mọi thuộc tính JSON.

Với Merge Patch, server kiểm tra các trường được yêu cầu thay đổi và những trường bị tác động bởi việc thay cả object hoặc mảng. Với JSON Patch, server kiểm tra cả `path` và `from`. Ví dụ `copy` từ một trường riêng tư sang trường được phép sửa vẫn có thể làm lộ dữ liệu nếu chỉ kiểm tra đích.

Một chính sách cho API hồ sơ:

| Vùng dữ liệu | Chính sách minh hoạ |
| --- | --- |
| `/displayName`, `/phone` | Chủ hồ sơ hoặc nhân viên được uỷ quyền |
| `/address` và các trường con được khai báo | Kiểm tra quyền chỉnh địa chỉ và tính hợp lệ của địa chỉ cuối |
| `/tags` | Giới hạn nhãn nào từng nhóm người dùng được thay đổi |
| `/id`, `/ownerId`, `/roles` | Không cho sửa qua endpoint hồ sơ |
| Đường dẫn root | Từ chối thay toàn bộ tài liệu trong hợp đồng này |
| Trường hồ sơ chưa được khai báo | Từ chối để tránh nhận nhầm thay đổi |

Không dùng phép kiểm tra chuỗi kiểu `startsWith("/address")` như toàn bộ cơ chế phân quyền: nó có thể chấp nhận nhầm `/addressBook`. Phân tích JSON Pointer rồi kiểm tra từng thành phần đường dẫn và thao tác thực tế.

Ngoài quyền ghi, hãy xem quyền đọc của `test` và `from`; phản hồi thành công hay thất bại cũng có thể làm lộ thông tin. Giới hạn kích thước body, số thao tác, độ sâu JSON và chi phí sao chép giúp tránh một bản vá nhỏ về số dòng nhưng tốn tài nguyên lớn.

## 9. Minh hoạ trong Java/Spring

### 9.1. Khai báo media type tại controller

Spring MVC hỗ trợ `@PatchMapping` và điều kiện `consumes`/`produces` để định tuyến theo phương thức, kiểu request và kiểu response. Xem [tài liệu Spring về request mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html).

Đoạn dưới là khung controller cho cấu hình **Spring MVC dùng Jackson 2.x**. Các kiểu `CustomerPatchService`, `UpdatedCustomer` là hợp đồng ứng dụng cần triển khai; đây chưa phải một chương trình server độc lập.

```java
import com.fasterxml.jackson.databind.JsonNode;
import java.security.Principal;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
final class CustomerPatchController {
    private final CustomerPatchService service;

    CustomerPatchController(CustomerPatchService service) {
        this.service = service;
    }

    @PatchMapping(
        path = "/customers/{id}",
        consumes = "application/merge-patch+json",
        produces = "application/json"
    )
    ResponseEntity<JsonNode> patch(
        @PathVariable("id") long id,
        @RequestHeader(name = "If-Match", required = false) String ifMatch,
        @RequestBody JsonNode patch,
        Principal principal
    ) {
        UpdatedCustomer updated =
            service.mergePatch(id, ifMatch, patch, principal);

        // service đã commit; etag là header value có dấu nháy kép.
        return ResponseEntity.ok()
            .header("ETag", updated.etag())
            .body(updated.body());
    }
}
```

Để `If-Match` không bắt buộc ở binding giúp tầng service/exception handler chủ động trả 428 theo hợp đồng, thay vì chỉ nhận lỗi thiếu header mặc định của framework. Nếu dự án dùng một thế hệ Jackson khác, cần điều chỉnh import và bộ chuyển đổi JSON theo cấu hình dự án.

Annotation chỉ chọn handler. Nó không tự thực hiện Merge Patch, kiểm tra trường cấm hoặc giải quyết optimistic locking.

### 9.2. Phân biệt vắng mặt và null trước khi áp dụng

Ví dụ logic ở biên JSON, không dùng trực tiếp để cập nhật entity:

```java
if (patch.has("phone")) {
    JsonNode value = patch.get("phone");

    if (value.isNull()) {
        // Có gửi phone: null -> yêu cầu xoá thuộc tính phone.
    } else if (value.isTextual()) {
        // Có gửi giá trị mới -> kiểm tra và chuẩn hoá số điện thoại.
    } else {
        // Từ chối: kiểu dữ liệu không phù hợp hợp đồng hồ sơ.
    }
} else {
    // Không gửi phone -> giữ nguyên thông tin hiện có.
}
```

Nếu dùng `hasNonNull("phone")` làm điều kiện duy nhất, nhánh xoá sẽ biến mất. Nếu dùng DTO thông thường với field nullable, cần một cách biểu diễn riêng cho trạng thái “không được gửi”.

### 9.3. Ranh giới trách nhiệm của service

Có thể mô tả service bằng mã giả sau:

```text
mergePatch(id, ifMatch, patch, actor):
    yêu cầu actor đã được xác thực
    yêu cầu root patch là object
    bắt đầu transaction

    current = đọc hồ sơ và phiên bản
    kiểm tra actor được sửa hồ sơ này
    kiểm tra If-Match theo chính sách API
    kiểm tra các trường patch được phép sửa

    candidate = áp dụng RFC 7396 lên bản sao của current
    kiểm tra candidate còn đủ trường bắt buộc
    kiểm tra kiểu dữ liệu và các ràng buộc liên trường
    ánh xạ tường minh các trường được phép sang mô hình lưu trữ

    cập nhật với expectedVersion
    nếu xung đột: rollback và trả lỗi điều kiện phiên bản
    ghi audit/outbox cần thiết trong cùng transaction
    commit

    trả biểu diễn đã lưu và ETag tương ứng
```

Thư viện patch nên chịu trách nhiệm ngữ nghĩa định dạng; service chịu trách nhiệm quyền, quy tắc nghiệp vụ và lưu có điều kiện. Không cần viết lại trình thông dịch JSON Patch bằng chuỗi và các lệnh `Map.put` rời rạc.

Đặc biệt, Bean Validation trên một DTO patch chưa đủ nếu DTO đó bỏ qua nhiều trường. Hãy kiểm tra **trạng thái ứng viên cuối cùng**, nơi tên, địa chỉ và các ràng buộc liên trường cùng tồn tại.

## 10. Phản hồi thành công và lỗi

Ví dụ phản hồi sau khi chỉ đổi tên:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "customer-42-v9"

{
  "id": 42,
  "displayName": "An Nguyễn",
  "phone": "0900000042",
  "address": {
    "city": "Huế",
    "postalCode": "530000"
  },
  "tags": ["newsletter", "priority"]
}
```

Có thể chọn 204 nếu hợp đồng không trả body; 204 không mang nội dung phản hồi. Không trả 200 kèm dữ liệu ứng viên khi việc commit chưa thành công. Ý nghĩa các mã thành công và lỗi HTTP được mô tả trong [RFC 9110, mục 15](https://www.rfc-editor.org/rfc/rfc9110.html#section-15).

Bảng sau là cách ánh xạ được chọn cho API minh hoạ:

| Tình huống | HTTP status |
| --- | --- |
| JSON không đọc được hoặc cấu trúc thao tác patch sai | 400 |
| Chưa có thông tin xác thực hợp lệ | 401 |
| Người dùng không được sửa resource/trường được yêu cầu | 403 |
| Khách hàng không tồn tại theo chính sách endpoint | 404 |
| Endpoint không hỗ trợ phương thức PATCH | 405, kèm `Allow` |
| Media type bản vá không được hỗ trợ | 415 |
| Thiếu điều kiện cập nhật mà API bắt buộc | 428 |
| ETag gửi lên không còn khớp | 412 |
| Xung đột nghiệp vụ; hoặc `test` thất bại theo hợp đồng này | 409 |
| Bản vá đúng cấu trúc nhưng tạo ra hồ sơ không hợp lệ | 422 |

Các lỗi thao tác như xoá một đường dẫn không tồn tại cũng cần được phân loại và mô tả nhất quán. Đừng để exception nội bộ mặc định biến mọi lỗi patch thành 500.

Ví dụ envelope lỗi do ứng dụng tự định nghĩa:

```json
{
  "code": "CUSTOMER_PATCH_INVALID",
  "message": "Tên hiển thị không được xoá.",
  "violations": [
    {
      "path": "/displayName",
      "reason": "required"
    }
  ]
}
```

Với JSON Patch, có thể bổ sung vị trí thao tác bị lỗi để client đối chiếu. Tránh đưa toàn bộ bản vá, token hoặc giá trị nhạy cảm vào thông báo và log. Thông tin lỗi phải đủ để sửa request, đồng thời tôn trọng quyền đọc dữ liệu.

## 11. Mô tả hợp đồng trong OpenAPI

OpenAPI cho phép khai báo riêng schema theo media type trong request body và mô tả header/phản hồi. Đoạn trích dưới dùng cú pháp **OpenAPI 3.1**; xem [đặc tả OpenAPI 3.1.1](https://spec.openapis.org/oas/v3.1.1.html#request-body-object).

Ví dụ này mô tả một endpoint chỉ nhận Merge Patch cho `displayName` và `phone`, là phạm vi rút gọn của hồ sơ để làm rõ schema:

```yaml
paths:
  /customers/{id}:
    patch:
      summary: Sửa một phần hồ sơ khách hàng
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
        - name: If-Match
          in: header
          required: true
          description: ETag mạnh từ lần đọc hồ sơ gần nhất
          schema:
            type: string
          example: '"customer-42-v8"'
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema:
              type: object
              additionalProperties: false
              properties:
                displayName:
                  type: string
                  minLength: 1
                  maxLength: 100
                  pattern: '\S'
                phone:
                  type: [string, 'null']
                  description: Vắng mặt là giữ nguyên; null là xoá thuộc tính
            example:
              displayName: An Nguyễn
              phone: null
      responses:
        '200':
          description: Đã lưu; trả biểu diễn hồ sơ hiện tại
          headers:
            ETag:
              description: ETag của biểu diễn sau cập nhật
              schema:
                type: string
          content:
            application/json:
              schema:
                type: object
        '412':
          description: Phiên bản đã thay đổi; cần đọc lại hồ sơ
        '415':
          description: Không hỗ trợ media type của bản vá
        '422':
          description: Kết quả cập nhật vi phạm hợp đồng hồ sơ
        '428':
          description: Thiếu điều kiện cập nhật bắt buộc
```

Các trường cập nhật không đặt `required` chỉ vì chúng bắt buộc trong resource hoàn chỉnh: client được phép không sửa chúng. Trong ví dụ, `displayName` không chấp nhận null ngay ở schema, còn `phone` chấp nhận null để diễn tả xoá.

Khi mở rộng ra địa chỉ và nhãn, phải thêm schema tương ứng, giới hạn mảng và mô tả quyền. Đoạn trích chưa phải tài liệu OpenAPI hoàn chỉnh; tài liệu thực tế còn cần cấu hình xác thực, schema response/error và các mã lỗi của endpoint.

Schema không thay thế kiểm tra quyền hoặc ràng buộc nghiệp vụ. Nó cũng không tự áp dụng bản vá lên trạng thái hiện tại để biết kết quả cuối còn hợp lệ hay không.

## 12. Kiểm thử theo hợp đồng và trạng thái lưu

Các tình huống sau là hướng dẫn thực hành kiểm thử API. Mỗi ca lỗi cần kiểm tra cả response và dữ liệu sau request.

| Ca thực hành | Điều cần quan sát |
| --- | --- |
| Merge Patch chỉ đổi tên | Điện thoại, địa chỉ và nhãn được giữ nguyên |
| Không gửi `phone` rồi gửi `phone: null` | Hai request có hai tác động khác nhau |
| Gửi `tags: []` | Danh sách rỗng được lưu đúng theo hợp đồng |
| Sửa một trường con của địa chỉ | Trường còn lại giữ nguyên và địa chỉ cuối được kiểm tra |
| Xoá tên bắt buộc | Trả lỗi; hồ sơ trước request còn nguyên |
| Gửi trường quản trị như `roles` | Bị từ chối, không được ánh xạ vào entity |
| JSON Patch có thao tác đầu hợp lệ, thao tác sau lỗi | Không lưu tác động của thao tác đầu |
| Hai request dùng cùng ETag và đồng thời commit | Chỉ một cập nhật vượt qua điều kiện phiên bản |
| Gửi media type sai | 415; không cố đoán định dạng từ hình dạng JSON |
| `copy` từ đường dẫn không được đọc | Không làm lộ dữ liệu qua trường đích |
| Timeout sau commit rồi gửi lại | Client xử lý được kết quả không chắc chắn theo hợp đồng retry |

Trong kiểm thử Spring, có thể gửi request bằng MockMvc để kiểm tra binding, media type và ánh xạ lỗi. Ca tranh chấp phiên bản cần bài kiểm thử tích hợp với cơ chế lưu trữ thực tế; mock một repository luôn báo thành công không chứng minh được khả năng chống lost update.

Với dữ liệu nhạy cảm, hãy dùng hồ sơ giả và kiểm tra log không chứa token hay giá trị riêng tư. Việc kiểm thử chức năng PATCH cần bao gồm trạng thái không được thay đổi ngoài phạm vi request.

## 13. Những lỗi thiết kế thường gặp

**Gửi một phần body nhưng dùng PUT như cập nhật chọn lọc.** Điều này làm client khó biết trường bị bỏ qua sẽ được giữ hay xoá. Hãy đặt rõ hợp đồng thay thế và hợp đồng bản vá cho từng endpoint.

**Gọi một JSON object là Merge Patch nhưng bỏ qua null.** Người dùng sẽ không xoá được thuộc tính dù client gửi đúng định dạng. Cần giữ thông tin trường có được gửi hay không từ đầu quá trình xử lý.

**Áp dụng patch trực tiếp lên entity rồi mới kiểm tra.** Khi thao tác sau thất bại, tác động trước có thể đã len vào persistence context. Hãy dựng trạng thái ứng viên và chỉ lưu sau khi toàn bộ yêu cầu được chấp nhận.

**Cho sửa mọi trường vì đã có đăng nhập.** Kiểm tra đăng nhập không thay thế quyền sửa từng vùng dữ liệu. Ánh xạ tường minh trường được phép và kiểm tra cả nguồn của thao tác di chuyển/sao chép.

**Dùng ETag nhưng ghi dữ liệu vô điều kiện.** Phép kiểm tra ở đầu request có thể đúng trong khi lúc commit dữ liệu đã đổi. Cơ chế lưu phải phát hiện được tình huống này.

**Tự retry mọi PATCH khi mạng lỗi.** Thao tác nối mảng có thể lặp tác động. Thiết kế client dựa trên ngữ nghĩa bản vá, điều kiện phiên bản và cơ chế nhận diện request nếu API có hỗ trợ.

Một endpoint PATCH hoàn chỉnh kết nối được bốn phần: **ý định cập nhật của client, định dạng bản vá đã công bố, quyền và quy tắc trên trạng thái cuối, cơ chế lưu nguyên tử có kiểm soát phiên bản**. Chọn thư viện là bước triển khai sau khi bốn phần này đã có hợp đồng rõ ràng.

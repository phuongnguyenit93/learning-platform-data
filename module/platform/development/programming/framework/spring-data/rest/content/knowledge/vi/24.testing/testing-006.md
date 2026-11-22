# Kiểm tra JSON Patch, Merge Patch, trường bị bỏ qua và giá trị null

Spring Data REST hỗ trợ `PATCH` trên item resource để cập nhật một phần entity. Khi kiểm thử, cần phân biệt định dạng patch, trường bị lược khỏi request, trường được gửi với giá trị `null`, và các thuộc tính không được phép ghi. Bốn trường hợp này có thể tạo ra kết quả khác nhau dù payload đều là JSON.

Bài này dùng ví dụ resource `/customers/42` với các thuộc tính `name`, `nickname`, `note`, `address`, `id` và `version`. Hãy thay bằng endpoint và mô hình domain của ứng dụng thực tế.

## 1. Phân biệt PUT và các dạng PATCH

Spring Data REST hiện liệt kê các media type sau cho `PATCH`:

- `application/json` — partial update theo cơ chế binding của Spring Data REST.
- `application/patch+json` — JSON Patch theo tài liệu Spring Data REST.
- `application/merge-patch+json` — JSON Merge Patch theo RFC 7396.
- `application/hal+json` — representation HAL.

RFC 6902 đăng ký media type chuẩn của JSON Patch là `application/json-patch+json`. Tài liệu Spring Data REST hiện liệt kê `application/patch+json`; một số security advisory của Spring cũng nhắc đến `application/json-patch+json`. Vì vậy, kiểm tra media type mà đúng phiên bản ứng dụng chấp nhận. Nếu nhận `415 Unsupported Media Type`, xem lại converter và media type của release đang chạy.

| Request | Ý nghĩa | Trường không xuất hiện trong payload |
|---|---|---|
| `PUT application/json` | Thay thế state của resource theo semantics PUT | Phải gửi representation đầy đủ; không dựa vào hành vi giữ nguyên của PATCH |
| `PATCH application/json` | Spring Data REST áp dụng partial update lên entity hiện có | Giữ nguyên field không được gửi |
| JSON Patch | Thực hiện danh sách operation trên JSON document | Không có operation cho field thì field đó không đổi |
| JSON Merge Patch | Merge object patch vào JSON representation hiện tại | Member bị lược khỏi patch giữ nguyên |

Không nhầm `Content-Type` với `Accept`: Content-Type xác định định dạng patch client gửi; Accept xác định representation response client muốn nhận.

## 2. Trường bị lược khỏi request khác với null

Giả sử dữ liệu ban đầu:

~~~json
{
  "id": 42,
  "name": "An",
  "nickname": "Annie",
  "note": "Gọi sau 18 giờ",
  "address": {
    "city": "Ho Chi Minh City",
    "street": "Le Loi"
  },
  "version": 5
}
~~~

Với partial update, nếu client chỉ gửi:

~~~json
{
  "name": "Binh"
}
~~~

thì `name` được đổi thành `Binh`; `nickname`, `note` và `address` không được gửi nên cần giữ nguyên.

Nếu client gửi:

~~~json
{
  "name": "Binh",
  "nickname": null
}
~~~

thì `nickname` đã được gửi một cách tường minh với giá trị JSON null. Đây là một chỉ thị khác với việc không có key `nickname` trong payload.

Trong Java, thuộc tính reference có thể nhận null; thuộc tính primitive như `int` hoặc `boolean` không thể giữ trạng thái null. Nếu nghiệp vụ cần phân biệt rõ “không gửi”, “xóa giá trị” và “gán null”, hãy dùng wrapper/nullable type hoặc DTO có cơ chế biểu diễn presence riêng.

Với `PATCH application/json` của Spring Data REST, `DomainObjectReader` áp dụng ObjectNode lên entity hiện tại, vì vậy field bị lược khỏi object patch được giữ nguyên. Field có mặt với giá trị null được binding như một giá trị được gửi tường minh, nếu thuộc tính có thể ghi và cho phép null. Validation, Jackson mapping, kiểu Java và ràng buộc persistence vẫn có thể từ chối hoặc biến đổi kết quả; phải đọc lại entity sau cập nhật để xác nhận.

## 3. JSON Patch: operation xác định chính xác thay đổi

JSON Patch theo RFC 6902 là một mảng operation. Các operation được áp dụng tuần tự theo đúng thứ tự trong mảng. Mỗi operation có `op` và `path`; một số operation cần thêm `value` hoặc `from`.

Sáu operation chuẩn:

| Operation | Tác dụng | Điều kiện quan trọng |
|---|---|---|
| `add` | Thêm object member hoặc chèn phần tử vào array; nếu object member đã có thì thay giá trị | Object cha/array phải tồn tại |
| `remove` | Xóa member hoặc phần tử tại path | Target phải tồn tại |
| `replace` | Thay giá trị tại path | Target phải tồn tại |
| `move` | Xóa ở `from` rồi thêm vào `path` | `from` phải tồn tại; không move vào chính hậu duệ của nó |
| `copy` | Sao chép giá trị từ `from` sang `path` | `from` phải tồn tại |
| `test` | Kiểm tra giá trị hiện tại bằng `value` | Sai khác thì patch thất bại |

Ví dụ đổi tên và kiểm tra trạng thái trước khi áp dụng:

~~~json
[
  { "op": "test", "path": "/status", "value": "ACTIVE" },
  { "op": "replace", "path": "/name", "value": "Binh" }
]
~~~

Ví dụ thêm một note:

~~~json
[
  { "op": "add", "path": "/note", "value": "Đã xác nhận" }
]
~~~

Nếu `note` đã tồn tại, `add` trên object member sẽ thay giá trị hiện tại. Đối với array, `add` chèn phần tử tại index và các phần tử phía sau dịch sang phải; path `/-` thêm vào cuối array.

### 3.1. replace null và remove không giống nhau

JSON Patch phân biệt rõ hai ý định:

~~~json
[
  { "op": "replace", "path": "/nickname", "value": null }
]
~~~

Operation này đặt giá trị JSON của member `nickname` thành null.

~~~json
[
  { "op": "remove", "path": "/nickname" }
]
~~~

Operation này xóa member `nickname` khỏi JSON document. Khi map document trở lại entity Java, cả hai trường hợp có thể cùng biểu hiện thành thuộc tính Java null; nếu cần phân biệt, kiểm tra cả representation JSON và kiểu dữ liệu/persistence mà ứng dụng dùng.

### 3.2. Path là JSON Pointer

Path dùng JSON Pointer, bắt đầu bằng `/`. Một số ví dụ:

- `/address/city` — thuộc tính lồng nhau.
- `/items/0/quantity` — field trong phần tử đầu tiên của array.
- `/profile~1name` — tên member có dấu `/`.
- `/labels/a~0b` — tên member có dấu `~`.

Trong JSON Pointer, escape `~` thành `~0` và `/` thành `~1`. Path sai, target không tồn tại cho `remove`/`replace`, hoặc operation không hợp lệ phải làm patch thất bại.

RFC 6902 yêu cầu các operation được thực hiện theo thứ tự và HTTP PATCH có tính atomic: nếu một operation thất bại, toàn bộ patch không được xem là thành công. Hãy kiểm tra dữ liệu lưu cuối cùng để bảo đảm operation trước đó không bị commit một phần.

## 4. JSON Merge Patch: object mô tả state muốn thay đổi

JSON Merge Patch theo RFC 7396 dùng một object có hình dạng gần giống JSON resource. Member xuất hiện trong patch được thêm hoặc thay thế; member không xuất hiện được giữ nguyên; giá trị null có ý nghĩa xóa member hiện tại.

Dữ liệu ban đầu:

~~~json
{
  "name": "An",
  "nickname": "Annie",
  "address": {
    "city": "Ho Chi Minh City",
    "street": "Le Loi"
  },
  "tags": ["vip", "newsletter"]
}
~~~

Patch:

~~~json
{
  "name": "Binh",
  "nickname": null,
  "address": {
    "city": "Da Nang"
  },
  "tags": ["vip"]
}
~~~

Kết quả JSON theo RFC 7396:

~~~json
{
  "name": "Binh",
  "address": {
    "city": "Da Nang",
    "street": "Le Loi"
  },
  "tags": ["vip"]
}
~~~

Các điểm cần kiểm tra:

- `name` được thay bằng giá trị mới.
- `nickname: null` xóa member khỏi JSON document.
- `address.city` được cập nhật; `address.street` không xuất hiện nên giữ nguyên.
- Array `tags` được thay thế toàn bộ, không merge từng phần tử.
- Member khác không có trong patch vẫn giữ nguyên.

Merge Patch không thể biểu đạt “đặt member thành JSON null” vì null đã dành cho ý nghĩa xóa member. Nếu API phải phân biệt member tồn tại với giá trị null và member không tồn tại, hãy dùng JSON Patch `replace value: null`, một DTO/command riêng hoặc một hợp đồng API khác phù hợp.

Nếu toàn bộ Merge Patch document là scalar, array hoặc null thay vì object, RFC 7396 định nghĩa kết quả là thay thế toàn bộ target bằng giá trị đó. Với entity resource, thông thường nên gửi object patch.

Khi Merge Patch được map về entity Java, một member bị xóa thường được biểu hiện thành thuộc tính null hoặc không xuất hiện trong serialized response tùy mapping và cấu hình Jackson. Đừng chỉ nhìn response JSON để kết luận persistence: kiểm tra giá trị trong repository/database và kiểm tra cả GET representation.

## 5. Ma trận kiểm thử omitted, null và field không được ghi

Dùng một fixture có giá trị khác null trước mỗi test để quan sát được thay đổi.

| Trường hợp | PATCH application/json | JSON Patch | JSON Merge Patch |
|---|---|---|---|
| Field bị lược khỏi request | Giữ nguyên | Không có operation nên giữ nguyên | Giữ nguyên |
| Field gửi giá trị mới | Binding giá trị mới | `replace` hoặc `add` | Member được thay bằng giá trị mới |
| Field gửi null | Binding null nếu writable/nullable | `replace value: null` đặt JSON null | Null xóa member theo RFC 7396 |
| Field bị xóa | Không có cú pháp remove chuẩn riêng; dùng null nếu nghiệp vụ chấp nhận | `remove` | Gửi member với null |
| Nested object chỉ gửi một member | Spring Data REST merge object lên object hiện tại; kiểm tra association cụ thể | Chỉ path được chỉ định thay đổi | Merge đệ quy các object |
| Array chỉ gửi một phần tử | Có thể bị binding thay cả collection tùy mapping; phải test | Chèn/xóa/thay theo index | Thay toàn bộ array |

Bảng này mô tả semantics của payload. Kết quả cuối cùng còn phụ thuộc vào kiểu Java, Jackson, persistent mapping, association handling, validation và phiên bản Spring Data REST.

### 5.1. Kiểm tra field bị bỏ qua hoặc read-only

Tạo fixture có một field chỉ đọc, ví dụ audit code:

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private String auditCode;
~~~

Có thể dùng `@JsonIgnore` cho field không được xuất bản hoặc không được binding theo hợp đồng của ứng dụng. Sau đó thử cập nhật field bằng cả ba dạng PATCH và xác nhận:

- Giá trị audit vẫn không đổi.
- Client không thể thay đổi field chỉ đọc thông qua nested path.
- Response status và error body khớp với chính sách bảo vệ field của phiên bản đang chạy.
- Repository/database không bị ghi giá trị do client gửi vào.

Nếu field không xuất hiện trong representation, không giả định rằng việc đoán tên JSON property sẽ cho phép ghi nó. Kiểm thử cả path trực tiếp và path lồng nhau.

### 5.2. Bảo vệ identifier và version

Các thuộc tính `@Id` và `@Version` là metadata quan trọng của persistence. Không cho client tự ý thay đổi chúng qua patch payload.

Ví dụ request JSON Patch cần được kiểm tra:

~~~json
[
  { "op": "replace", "path": "/id", "value": 999 },
  { "op": "replace", "path": "/version", "value": 999 }
]
~~~

Sau request, xác nhận:

- Identifier của entity vẫn giữ nguyên.
- Không có entity khác bị ghi đè.
- Version do persistence layer quản lý, không nhận giá trị tùy ý từ client.
- Optimistic locking vẫn phát hiện cập nhật đồng thời.

Đây là regression test bảo mật quan trọng. CVE-2026-47849 ghi nhận JSON Patch có thể sửa trực tiếp identifier và version trên các phiên bản bị ảnh hưởng; PUT và Merge Patch đã có đường binding bỏ qua các thuộc tính này, nhưng JSON Patch thiếu guard tương đương. Advisory nêu các phiên bản bị ảnh hưởng và bản sửa trong mục Tài liệu tham khảo. Hãy nâng cấp đúng nhánh đã vá trước khi dựa vào test này như một biện pháp bảo vệ.

### 5.3. Bảo vệ nested read-only path

Không chỉ kiểm tra field cuối cùng của path. Với model có container lồng nhau được đánh dấu read-only, thử path như `/settings/0/value` hoặc `/metadata/key` để bảo đảm các segment trung gian cũng tôn trọng quyền ghi.

CVE-2026-41728 mô tả trường hợp JSON Patch bỏ qua write-access filter ở intermediate path segments khi xử lý JSON Pointer nhiều cấp. Thêm regression test cho embedded object, collection và map có container read-only; kiểm tra cả dữ liệu persisted lẫn response. Nâng cấp bản Spring Data REST đã vá theo advisory.

## 6. Gửi request thử bằng curl

Các lệnh dưới đây giả định endpoint item resource là `/customers/42`. Thay path, field và giá trị theo fixture của ứng dụng.

**Spring Data REST partial JSON: giữ field bị lược**

~~~bash
curl -i -X PATCH "http://localhost:8080/customers/42" -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"name":"Binh"}'
~~~

Đọc lại resource để xác nhận các field khác còn nguyên.

**JSON Patch: đổi field và đặt null**

~~~bash
curl -i -X PATCH "http://localhost:8080/customers/42" -H "Content-Type: application/patch+json" -H "Accept: application/hal+json" -d '[{"op":"replace","path":"/name","value":"Binh"},{"op":"replace","path":"/nickname","value":null}]'
~~~

Tài liệu Spring Data REST hiện liệt kê `application/patch+json`. Nếu release đang dùng đăng ký trực tiếp media type chuẩn RFC 6902, có thể kiểm tra `application/json-patch+json`; không tự đổi body JSON Patch thành object Merge Patch.

**JSON Patch: xóa member**

~~~bash
curl -i -X PATCH "http://localhost:8080/customers/42" -H "Content-Type: application/patch+json" -H "Accept: application/hal+json" -d '[{"op":"remove","path":"/nickname"}]'
~~~

**JSON Merge Patch: field bị lược giữ nguyên, null xóa member**

~~~bash
curl -i -X PATCH "http://localhost:8080/customers/42" -H "Content-Type: application/merge-patch+json" -H "Accept: application/hal+json" -d '{"name":"Binh","nickname":null,"address":{"city":"Da Nang"}}'
~~~

Sau mỗi request, gửi GET mới tới đúng URI và kiểm tra dữ liệu thực tế. Không kết luận chỉ từ status code vì Spring Data REST có thể trả body hoặc 204 tùy cấu hình response.

## 7. Kiểm thử tích hợp bằng MockMvc

Nên kiểm thử qua HTTP layer để bao gồm converter, Jackson, Spring Data REST, validation, repository và event handler. Mỗi test tạo một entity fixture độc lập rồi kiểm tra cả repository và GET representation sau PATCH.

Ví dụ khung test cho Merge Patch:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerPatchIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    CustomerRepository repository;

    @Test
    void mergePatchKeepsOmittedFieldsAndClearsNullMember() throws Exception {
        Customer customer = repository.save(
            new Customer("An", "Annie", "Gọi sau 18 giờ")
        );

        mockMvc.perform(patch("/customers/{id}", customer.getId())
                .contentType(MediaType.valueOf("application/merge-patch+json"))
                .accept(MediaType.parseMediaType("application/hal+json"))
                .content("""
                    {
                      "name": "Binh",
                      "nickname": null
                    }
                    """))
            .andExpect(status().is2xxSuccessful());

        Customer actual = repository.findById(customer.getId())
            .orElseThrow();

        assertThat(actual.getName()).isEqualTo("Binh");
        assertThat(actual.getNickname()).isNull();
        assertThat(actual.getNote()).isEqualTo("Gọi sau 18 giờ");
    }
}
~~~

Đây là khung minh họa; điều chỉnh constructor, repository, media type và status theo phiên bản cùng cấu hình ứng dụng. Nếu dùng database transaction trong test, bảo đảm assertion đọc được dữ liệu đã được request xử lý, không chỉ dữ liệu trong persistence context cũ.

### Bộ test tối thiểu nên có

1. PATCH application/json chỉ gửi một field; các field khác vẫn giữ nguyên.
2. PATCH application/json gửi null vào field nullable; field được binding thành null.
3. JSON Patch replace một field; giá trị mới được lưu.
4. JSON Patch replace value null; phân biệt với remove ở document layer.
5. JSON Patch remove một field tồn tại; xác nhận member bị xóa và entity state đúng kỳ vọng.
6. JSON Patch replace/remove một path không tồn tại; patch thất bại và không có thay đổi một phần.
7. JSON Patch test thành công; patch tiếp tục thực hiện các operation sau.
8. JSON Patch test thất bại sau một operation thay đổi; xác nhận toàn bộ patch không được lưu một phần.
9. JSON Merge Patch bỏ qua một field; field giữ nguyên.
10. JSON Merge Patch gửi null; member bị xóa theo RFC 7396 và entity mapping được xác nhận.
11. JSON Merge Patch cập nhật nested object; sibling field không gửi vẫn còn.
12. JSON Merge Patch gửi array; xác nhận toàn bộ array được thay thế.
13. Mọi dạng PATCH đều không ghi được field read-only, identifier và version.
14. JSON Patch không thể sửa nested path đi qua container read-only.
15. Field có validation như `@NotNull` bị gửi null; xác nhận validation và dữ liệu persisted theo đúng hợp đồng.
16. Field không xuất hiện trong response do `@JsonInclude(NON_NULL)`; kiểm tra repository để phân biệt null với member bị ẩn khi serialize.

## 8. Lỗi thường gặp khi kiểm thử

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| 415 Unsupported Media Type | Content-Type không được converter của release hỗ trợ | Dùng media type trong tài liệu đúng phiên bản; kiểm tra `application/patch+json` và `application/merge-patch+json` |
| 400 Bad Request | JSON sai cú pháp, operation/path sai hoặc binding thất bại | Đọc error response và kiểm tra JSON Pointer |
| Field bị lược nhưng bị xóa | Client đang dùng PUT hoặc custom mapper thay semantics PATCH | Kiểm tra method, Content-Type và binding handler |
| null không xóa member như mong đợi | Đang dùng `application/json` hoặc JSON Patch replace null | Phân biệt Merge Patch null với JSON null |
| Array bị mất phần tử không gửi | Merge Patch thay toàn bộ array | Gửi array đầy đủ hoặc dùng JSON Patch theo index |
| Patch operation trước đã thay đổi dữ liệu dù operation sau lỗi | Patch handler/custom code không giữ atomicity hoặc test chưa cô lập transaction | Kiểm tra persistence sau lỗi và nâng cấp/fix handler |
| Read-only field bị đổi qua path lồng nhau | Filter không áp dụng ở intermediate path segment hoặc phiên bản có lỗ hổng | Kiểm tra CVE-2026-41728 và regression test |
| Identifier/version bị đổi qua JSON Patch | Phiên bản bị ảnh hưởng bởi CVE-2026-47849 | Nâng cấp bản vá; kiểm thử lại `@Id` và `@Version` |

Một lỗi thực tế cần lưu ý khi nâng cấp: issue Spring Data REST #2596 báo cáo Merge Patch với array phần tử có linkable association có thể giữ association cũ khi cập nhật phần tử đã tồn tại từ nhánh 4.3. Nếu aggregate có collection of embeddables và association dạng link, thêm test riêng cho association trong phần tử cũ và xác minh theo đúng release đang dùng.

## 9. Quy trình kiểm tra một thay đổi PATCH

1. Tạo fixture với mọi field cần kiểm tra đều có giá trị ban đầu khác null.
2. GET resource và lưu representation ban đầu.
3. Gửi một request PATCH với đúng Content-Type; mỗi test chỉ kiểm tra một semantics.
4. Ghi nhận status và error body.
5. Đọc lại qua repository để xác minh giá trị persistence.
6. GET resource lần nữa để xác minh representation, bao gồm field bị omit/null theo Jackson.
7. Với request thất bại, xác nhận không có thay đổi một phần.
8. Lặp lại trên các field nested, array, association, read-only, id và version.
9. Chạy test trên đúng phiên bản Spring Data REST và dependency set đang triển khai.

## Tài liệu tham khảo

- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): các HTTP method, media type được hỗ trợ và semantics của PATCH.
- [Spring Data REST — DomainObjectReader API](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/json/DomainObjectReader.html): áp dụng ObjectNode lên domain object hiện có và phân biệt read với readPut.
- [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902.html): sáu operation, JSON Pointer, thứ tự thực hiện và xử lý lỗi atomic.
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396.html): member bị lược, ý nghĩa xóa của null, merge object và thay toàn bộ array.
- [CVE-2026-41728 — JSON Patch bypasses read-only property protection](https://spring.io/security/cve-2026-41728/): lỗ hổng ở intermediate path segments và các phiên bản đã sửa.
- [CVE-2026-47849 — JSON Patch can mutate identifier and version](https://spring.io/security/cve-2026-47849/): bảo vệ `@Id`, `@Version`, phạm vi phiên bản bị ảnh hưởng và bản sửa.
- [Spring Data REST issue #2596](https://github.com/spring-projects/spring-data-rest/issues/2596): regression report về linkable association trong array khi dùng Merge Patch.

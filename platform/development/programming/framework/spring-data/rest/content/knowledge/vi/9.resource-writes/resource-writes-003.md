# PUT thay thế tài nguyên và tác động lên thuộc tính bị bỏ qua

Trong Spring Data REST, **PUT** được dùng để thay thế biểu diễn của một tài nguyên hiện có. Client gửi một representation mới cho tài nguyên; vì vậy request PUT cần chứa đầy đủ các thuộc tính có thể ghi mà client muốn duy trì.

Điểm dễ gây mất dữ liệu là một thuộc tính đang có giá trị trong database nhưng lại bị bỏ qua khỏi body PUT. Khi representation mới được bind vào entity, thuộc tính không được gửi có thể nhận giá trị null, giá trị mặc định hoặc trạng thái rỗng tùy kiểu dữ liệu và cách ứng dụng cấu hình. Nếu chỉ muốn thay đổi một vài thuộc tính, hãy cân nhắc dùng **PATCH**.

## 1. PUT trong Spring Data REST

Spring Data REST tự động xuất repository thành tài nguyên REST. Với một tài nguyên collection **customers**, mỗi bản ghi có thể được truy cập qua URL item, ví dụ:

~~~http
GET /customers/42
~~~

Client có thể lấy representation hiện tại, chỉnh sửa và gửi lại bằng PUT:

~~~http
PUT /customers/42
Content-Type: application/json
Accept: application/hal+json
~~~

PUT biểu thị việc gửi representation mới cho tài nguyên tại URI đó. Vì vậy, client nên gửi toàn bộ các trường có thể ghi mà muốn giữ lại sau khi cập nhật.

Ví dụ, representation hiện tại của customer có thể gồm:

~~~json
{
  "name": "Lan",
  "email": "lan@example.com",
  "phone": "0901234567",
  "city": "Da Nang",
  "active": true
}
~~~

Nếu client muốn đổi tên nhưng vẫn giữ email, số điện thoại, thành phố và trạng thái, body PUT nên chứa đầy đủ các trường đó:

~~~http
PUT /customers/42
Content-Type: application/json
Accept: application/hal+json
~~~

~~~json
{
  "name": "Lan Nguyen",
  "email": "lan@example.com",
  "phone": "0901234567",
  "city": "Da Nang",
  "active": true
}
~~~

Sau khi cập nhật thành công, representation của item phản ánh dữ liệu mới đã được lưu.

## 2. Điều gì xảy ra với thuộc tính bị bỏ qua?

Giả sử customer hiện tại có:

| Thuộc tính | Giá trị đang lưu |
|---|---|
| name | Lan |
| email | lan@example.com |
| phone | 0901234567 |
| city | Da Nang |
| active | true |

Client gửi PUT chỉ có một phần dữ liệu:

~~~json
{
  "name": "Lan Nguyen",
  "email": "lan@example.com"
}
~~~

Body này mô tả representation mới nhưng thiếu **phone**, **city** và **active**. Các trường bị bỏ qua có thể bị đặt lại khi request được bind và lưu:

- Trường tham chiếu như **String**, **Integer** hoặc **Boolean** có thể nhận **null** nếu không có giá trị mới.
- Trường kiểu nguyên thủy như **int** hoặc **boolean** có thể nhận giá trị mặc định của Java, lần lượt là **0** và **false**.
- Collection hoặc association có thể trở thành rỗng, null hoặc bị gỡ liên kết tùy cách ánh xạ entity và xử lý quan hệ.
- Constructor, setter, Jackson configuration, custom deserializer và logic nghiệp vụ có thể ảnh hưởng đến kết quả bind cuối cùng.

Do đó, không nên giả định rằng trường bị bỏ qua sẽ tự động giữ nguyên giá trị cũ trong database. Hãy xem body PUT là representation đầy đủ mà client muốn lưu và gửi rõ các trường cần duy trì.

### Ví dụ về nguy cơ mất dữ liệu

Entity có thể được khai báo như sau:

~~~java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private String email;
    private String phone;
    private String city;
    private boolean active;

    // getters and setters
}
~~~

Nếu request chỉ gửi **name** và **email**, các thuộc tính khác có thể được bind thành null hoặc giá trị mặc định. Khi entity được lưu, dữ liệu cũ của **phone**, **city** hoặc **active** có thể bị mất hoặc thay đổi.

Với kiểu **boolean** nguyên thủy, giá trị mặc định là **false**. Với **Boolean** dạng wrapper, giá trị thiếu có thể là **null**. Sự khác nhau này quan trọng nếu ứng dụng cần phân biệt trạng thái false với trạng thái chưa được cung cấp.

## 3. Gửi đầy đủ representation khi dùng PUT

Một quy trình an toàn cho client là:

1. Gửi GET để đọc representation hiện tại.
2. Lấy các trường có thể ghi và cần duy trì.
3. Áp dụng thay đổi vào representation đó.
4. Gửi PUT với body đầy đủ tới URI của item.
5. Đọc lại tài nguyên hoặc kiểm tra response để xác nhận dữ liệu đã được lưu như mong muốn.

Ví dụ:

~~~http
GET /customers/42
Accept: application/hal+json
~~~

Sau khi đọc dữ liệu, client gửi toàn bộ các trường cần giữ:

~~~http
PUT /customers/42
Content-Type: application/json
Accept: application/hal+json
~~~

~~~json
{
  "name": "Lan Nguyen",
  "email": "lan@example.com",
  "phone": "0901234567",
  "city": "Da Nang",
  "active": true
}
~~~

Nếu một thuộc tính cần được xóa có chủ đích, hãy thể hiện rõ ý định đó theo contract của API, chẳng hạn gửi **null** cho trường nullable nếu endpoint hỗ trợ. Đừng dựa vào việc vô tình bỏ qua trường để diễn đạt yêu cầu xóa dữ liệu.

Không nhất thiết phải gửi những trường chỉ do server quản lý hoặc không được phép ghi. Ví dụ ID trong URI, trường audit, giá trị tính toán, version hoặc thuộc tính được đánh dấu chỉ đọc nên tuân theo contract mà API công bố.

## 4. So sánh PUT và PATCH

PUT và PATCH đều có thể dùng để cập nhật một tài nguyên, nhưng ý nghĩa của request khác nhau:

| Tiêu chí | PUT | PATCH |
|---|---|---|
| Ý nghĩa | Thay thế representation của tài nguyên | Thay đổi một phần tài nguyên |
| Body | Gửi đầy đủ các trường có thể ghi cần giữ | Chỉ gửi các trường muốn thay đổi theo định dạng PATCH được hỗ trợ |
| Trường không có trong body | Có thể bị đặt lại theo quy tắc binding và thay thế | Thông thường giữ nguyên nếu không nằm trong thay đổi |
| Khi nên dùng | Client có representation đầy đủ | Client chỉ thay đổi một vài trường |

Ví dụ muốn chỉ đổi tên customer:

**PUT — gửi lại representation đầy đủ:**

~~~http
PUT /customers/42
Content-Type: application/json
~~~

~~~json
{
  "name": "Lan Nguyen",
  "email": "lan@example.com",
  "phone": "0901234567",
  "city": "Da Nang",
  "active": true
}
~~~

**PATCH — chỉ gửi phần thay đổi:**

~~~http
PATCH /customers/42
Content-Type: application/merge-patch+json
~~~

~~~json
{
  "name": "Lan Nguyen"
}
~~~

Với PATCH, các thuộc tính không được đề cập thường được giữ nguyên. Cách diễn giải **null**, collection và association còn phụ thuộc định dạng PATCH và cách Spring Data REST cùng ứng dụng xử lý request. Hãy kiểm tra media type và contract mà API thực tế hỗ trợ; không nên mặc định mọi kiểu PATCH đều có cùng quy tắc.

## 5. Giá trị null, giá trị mặc định và validation

Khi một thuộc tính bị bỏ qua trong PUT, kết quả có thể ảnh hưởng đến validation và ràng buộc lưu trữ.

Ví dụ entity có validation:

~~~java
@NotNull
private String email;
~~~

Nếu việc binding làm **email** thành null, quá trình validation có thể từ chối request. Tương tự, ràng buộc NOT NULL ở database có thể khiến thao tác lưu thất bại.

Một số điểm cần phân biệt:

- **@NotNull** là ràng buộc validation khi Bean Validation được kích hoạt.
- **@Column(nullable = false)** mô tả mapping và có thể ảnh hưởng schema; không nên xem nó là cơ chế validation duy nhất.
- Kiểu dữ liệu nguyên thủy có giá trị mặc định của Java, ví dụ **false** hoặc **0**.
- Kiểu wrapper và kiểu tham chiếu có thể biểu diễn null.
- Giá trị mặc định trong constructor không đảm bảo sẽ được dùng lại nếu quá trình binding gán giá trị khác.

Nếu request thất bại do validation hoặc persistence constraint, hãy đọc response và log phía server để xác định trường nào không hợp lệ. Không nên kết luận rằng dữ liệu đã được cập nhật chỉ vì client đã gửi request.

## 6. Quan hệ và collection trong representation

Entity có thể chứa quan hệ tới entity khác hoặc collection các phần tử con. Khi PUT thay thế representation, việc bỏ qua các trường quan hệ cần được xem xét cẩn thận.

Ví dụ customer có liên kết tới một địa chỉ:

~~~json
{
  "name": "Lan",
  "address": {
    "street": "Le Loi",
    "city": "Da Nang"
  }
}
~~~

Nếu body PUT bỏ qua **address**, cách xử lý liên kết phụ thuộc mapping entity và cơ chế binding của Spring Data REST. Liên kết có thể bị đặt lại hoặc giữ theo logic cụ thể của ứng dụng. Không nên dựa vào giả định rằng association luôn được giữ nguyên.

Với association được Spring Data REST xuất dưới dạng URI hoặc liên kết HAL, hãy dùng đúng hình thức mà endpoint công bố. Kiểm tra riêng các thao tác gán, thay thế hoặc xóa association; đừng coi một object JSON lồng nhau và một association link là hai cách biểu diễn tương đương trong mọi cấu hình.

Đối với collection như **orders**, **roles** hoặc **tags**, hãy xác định contract của endpoint: request có thay thế toàn bộ collection, thêm phần tử, hay cập nhật một association riêng. Nếu chỉ cần thay đổi một quan hệ, thao tác association resource chuyên biệt có thể phù hợp hơn việc gửi lại toàn bộ item.

## 7. Kiểm tra hành vi PUT trong ứng dụng

Có thể kiểm tra bằng một kịch bản nhỏ với dữ liệu đã biết.

**Bước 1 — Tạo hoặc chọn một customer có đủ dữ liệu**

Đảm bảo các trường **name**, **email**, **phone**, **city** và **active** đều có giá trị.

**Bước 2 — Đọc representation trước khi cập nhật**

~~~http
GET /customers/42
Accept: application/hal+json
~~~

Ghi lại giá trị của tất cả trường có thể ghi.

**Bước 3 — Gửi PUT có chủ ý bỏ qua một trường**

~~~http
PUT /customers/42
Content-Type: application/json
~~~

~~~json
{
  "name": "Lan Nguyen",
  "email": "lan@example.com"
}
~~~

**Bước 4 — Đọc lại tài nguyên**

~~~http
GET /customers/42
Accept: application/hal+json
~~~

So sánh **phone**, **city** và **active** với giá trị trước request. Kết quả cho thấy chính xác cách ứng dụng hiện tại bind và lưu các thuộc tính bị bỏ qua.

**Bước 5 — Thử PATCH để cập nhật một phần**

~~~http
PATCH /customers/42
Content-Type: application/merge-patch+json
~~~

~~~json
{
  "name": "Lan Tran"
}
~~~

Đọc lại tài nguyên để xác nhận các trường không được yêu cầu thay đổi vẫn giữ nguyên theo contract PATCH của ứng dụng.

Không nên chạy thử nghiệm bỏ qua trường trên dữ liệu production có giá trị. Dùng dữ liệu kiểm thử hoặc môi trường development để tránh thay đổi ngoài ý muốn.

## 8. Tránh ghi đè dữ liệu khi có nhiều client

Nếu hai client cùng đọc một tài nguyên rồi gửi PUT, request của client gửi sau có thể ghi đè thay đổi của client gửi trước.

Ví dụ:

1. Client A đọc customer khi **phone** có giá trị cũ.
2. Client B cập nhật **phone** và lưu thành công.
3. Client A gửi representation cũ bằng PUT để chỉ đổi **name**.
4. PUT của A có thể ghi lại **phone** cũ vì body chứa representation trước đó.

Để hạn chế cập nhật mất mát, ứng dụng có thể dùng optimistic locking với **@Version** và cơ chế ETag/conditional request nếu được cấu hình. Client nên gửi validator nhận được từ lần đọc trước, ví dụ **If-Match**, theo contract của endpoint. Khi representation đã thay đổi, server có thể từ chối request cũ thay vì ghi đè âm thầm.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Thuộc tính cũ trở thành null sau PUT | Body thiếu trường tham chiếu cần giữ | Gửi đầy đủ trường có thể ghi trong representation PUT |
| Boolean chuyển thành false | Trường kiểu boolean nguyên thủy bị bỏ qua khi binding | Gửi rõ giá trị hoặc dùng kiểu wrapper nếu nghiệp vụ cần trạng thái null |
| Request PUT bị validation từ chối | Trường bắt buộc bị thiếu hoặc nhận null | Kiểm tra body, validation annotation và response |
| Association bị gỡ hoặc thay đổi | Quan hệ không được gửi hoặc được biểu diễn sai contract | Kiểm tra association resource và định dạng liên kết |
| Một thay đổi của client khác bị ghi đè | Client gửi representation cũ bằng PUT | Dùng ETag/If-Match hoặc optimistic locking khi endpoint hỗ trợ |
| Chỉ muốn đổi một trường nhưng phải gửi nhiều trường | Đang dùng PUT cho cập nhật một phần | Dùng PATCH theo media type và contract API hỗ trợ |

## 10. Quy tắc lựa chọn

- Dùng **PUT** khi client có representation đầy đủ và muốn thay thế trạng thái tài nguyên.
- Trước PUT, đọc tài nguyên hiện tại hoặc xây dựng body đầy đủ từ dữ liệu đáng tin cậy.
- Gửi rõ các trường cần duy trì; đừng dựa vào việc trường bị bỏ qua sẽ tự giữ nguyên.
- Dùng **PATCH** khi chỉ muốn thay đổi một phần và endpoint hỗ trợ đúng định dạng PATCH cần dùng.
- Kiểm tra các trường nullable, primitive, collection và association vì chúng có thể có kết quả binding khác nhau.
- Dùng validation và optimistic locking phù hợp để tránh dữ liệu không hợp lệ hoặc cập nhật mất mát.

Hiểu rõ sự khác nhau giữa PUT và PATCH giúp client gửi đúng ý định cập nhật, tránh vô tình xóa dữ liệu và giữ cho contract REST nhất quán.

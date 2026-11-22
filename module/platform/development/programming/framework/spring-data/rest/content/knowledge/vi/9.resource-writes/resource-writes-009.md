# Phân biệt trường bị bỏ qua, giá trị null và thay thế mảng khi cập nhật

Khi cập nhật một tài nguyên qua Spring Data REST, ba trường hợp dễ bị nhầm lẫn là: không gửi một thuộc tính, gửi thuộc tính với giá trị JSON \`null\`, và gửi một mảng mới. Chúng có ý nghĩa khác nhau. Nếu hiểu sai, một yêu cầu PATCH tưởng như chỉ sửa một trường có thể vô tình xóa dữ liệu hoặc thay toàn bộ danh sách hiện có.

Cần xác định **kiểu PATCH và Content-Type** trước khi suy luận kết quả. Phần dưới tập trung vào hai định dạng patch có quy tắc rõ ràng: JSON Merge Patch và JSON Patch.

## 1. Chọn đúng kiểu cập nhật

| Cách gửi | Ý nghĩa chính | Khi nên dùng |
|---|---|---|
| PUT | Gửi biểu diễn đầy đủ để thay thế tài nguyên | Khi client có toàn bộ trạng thái cần lưu |
| PATCH với application/merge-patch+json | Mô tả các thay đổi theo cấu trúc JSON; thuộc tính không xuất hiện được giữ nguyên | Khi muốn cập nhật một số thuộc tính |
| PATCH với application/json-patch+json | Gửi danh sách thao tác có đường dẫn cụ thể như add, remove, replace | Khi cần điều khiển chính xác một thuộc tính hoặc phần tử mảng |

Đừng suy luận rằng mọi request PATCH đều có cùng quy tắc. Hãy gửi Content-Type tương ứng với định dạng patch mà endpoint Spring Data REST hỗ trợ và client đang sử dụng.

## 2. Thuộc tính bị bỏ qua: giữ nguyên giá trị hiện tại

Với JSON Merge Patch, một thuộc tính không xuất hiện trong tài liệu patch sẽ không bị thay đổi.

Ví dụ tài nguyên hiện tại:

~~~json
{
  "id": 42,
  "name": "Laptop",
  "description": "Thiết bị dùng cho văn phòng",
  "price": 1000,
  "tags": ["work", "portable"]
}
~~~

Request chỉ gửi tên mới:

~~~http
PATCH /products/42
Content-Type: application/merge-patch+json
Accept: application/hal+json
~~~

~~~json
{
  "name": "Laptop Pro"
}
~~~

Kết quả mong đợi:

- name được cập nhật thành Laptop Pro.
- description vẫn là Thiết bị dùng cho văn phòng.
- price vẫn là 1000.
- tags vẫn gồm work và portable.

Nói cách khác, trong Merge Patch, **không gửi thuộc tính có nghĩa là không yêu cầu thay đổi thuộc tính đó**. Đây là cách phù hợp để giữ nguyên các trường mà biểu mẫu hoặc client không chỉnh sửa.

Với JSON Patch, thuộc tính không có thao tác tương ứng trong mảng thao tác cũng được giữ nguyên.

## 3. Gửi null: yêu cầu xóa hoặc làm rỗng thuộc tính

Trong JSON Merge Patch, giá trị null có ý nghĩa xóa thuộc tính khỏi biểu diễn đích. Khi patch được ánh xạ vào entity, thao tác này thường tương ứng với việc làm rỗng thuộc tính, chẳng hạn gán null cho một field có thể null. Kết quả cuối cùng vẫn phụ thuộc vào kiểu dữ liệu, mapping, validation và quy tắc nghiệp vụ của ứng dụng.

Ví dụ:

~~~json
{
  "description": null
}
~~~

Sau patch, description được yêu cầu xóa/làm rỗng; các thuộc tính không xuất hiện như name, price và tags vẫn giữ nguyên.

Cần kiểm tra các điều kiện sau trước khi cho phép xóa giá trị:

- Field có cho phép null không? Ràng buộc như @NotNull hoặc nullable = false có thể khiến thao tác bị từ chối.
- Field có phải kiểu primitive Java như int hoặc long không? Primitive không biểu diễn được null; nếu cần khả năng xóa giá trị, cân nhắc kiểu wrapper như Integer hoặc Long.
- Field có phải quan hệ tới entity khác không? Việc đặt quan hệ thành null có thể bị validation hoặc quy tắc domain ngăn cản.
- Có cần phân biệt xóa thuộc tính khỏi JSON với việc lưu giá trị null trong database không? Hai trạng thái này có thể khác nhau tùy cách serialize và mô hình dữ liệu.

### null trong JSON Patch khác với remove

JSON Patch dùng thao tác tường minh nên có thể phân biệt hai ý định:

~~~json
[
  { "op": "remove", "path": "/description" },
  { "op": "replace", "path": "/name", "value": null }
]
~~~

- remove yêu cầu bỏ thuộc tính tại đường dẫn đó.
- replace với value là null yêu cầu thay giá trị tại đường dẫn bằng JSON null. Đường dẫn phải tồn tại để replace hợp lệ.

Vì vậy, khi cần phân biệt xóa thuộc tính với gán giá trị null, hãy chọn thao tác JSON Patch tương ứng thay vì dựa vào một payload mơ hồ.

## 4. Mảng trong JSON Merge Patch được thay thế toàn bộ

Mảng là trường hợp dễ gây mất dữ liệu nhất. Theo quy tắc JSON Merge Patch, mảng được xem là một giá trị nguyên khối. Mảng mới thay thế toàn bộ mảng cũ; các phần tử không được gửi lại sẽ biến mất.

Giả sử tài nguyên đang có:

~~~json
{
  "tags": ["work", "portable", "office"]
}
~~~

Client gửi:

~~~json
{
  "tags": ["work", "premium"]
}
~~~

Kết quả là:

~~~json
{
  "tags": ["work", "premium"]
}
~~~

Phần tử portable và office đã bị loại khỏi mảng vì client gửi một mảng thay thế.

Phân biệt ba payload sau:

| Payload | Kết quả với Merge Patch |
|---|---|
| Không có thuộc tính tags | Giữ nguyên mảng hiện tại |
| "tags": [] | Thay bằng mảng rỗng |
| "tags": ["work", "premium"] | Thay toàn bộ bằng mảng mới |
| "tags": null | Xóa thuộc tính tags khỏi biểu diễn đích |

Không có cơ chế tự động ghép phần tử theo vị trí, ID hoặc giá trị. Nếu client chỉ biết một phần danh sách, gửi mảng một phần có thể làm mất các phần tử còn lại.

### Cập nhật một phần tử mảng bằng JSON Patch

Nếu chỉ muốn sửa một phần tử hoặc thêm một phần tử vào cuối mảng, JSON Patch cho phép chỉ rõ đường dẫn:

~~~http
PATCH /products/42
Content-Type: application/json-patch+json
~~~

~~~json
[
  { "op": "replace", "path": "/tags/1", "value": "premium" },
  { "op": "add", "path": "/tags/-", "value": "featured" }
]
~~~

Với mảng ban đầu ["work", "portable", "office"], kết quả sẽ là ["work", "premium", "office", "featured"].

Một số thao tác thường dùng:

- replace /tags/1: thay phần tử tại chỉ số 1.
- add /tags/-: thêm phần tử vào cuối mảng.
- remove /tags/0: xóa phần tử tại chỉ số 0; các chỉ số phía sau dịch chuyển.

Chỉ số mảng bắt đầu từ 0. Nếu nhiều thao tác cùng thay đổi mảng, thứ tự thao tác có ảnh hưởng đến chỉ số của các phần tử tiếp theo. Không nên dùng chỉ số như một định danh ổn định khi dữ liệu có thể bị thay đổi đồng thời.

## 5. Ví dụ tổng hợp

Tài nguyên ban đầu:

~~~json
{
  "id": 42,
  "name": "Laptop",
  "description": "Thiết bị văn phòng",
  "price": 1000,
  "tags": ["work", "portable"],
  "stock": 5
}
~~~

Request Merge Patch:

~~~json
{
  "name": "Laptop Pro",
  "description": null,
  "tags": ["work", "premium"]
}
~~~

Đọc kết quả theo từng thuộc tính:

| Thuộc tính | Payload | Kết quả |
|---|---|---|
| name | Có giá trị mới | Đổi thành Laptop Pro |
| description | Có giá trị null | Yêu cầu xóa/làm rỗng; phụ thuộc khả năng nullable và mapping |
| price | Bị bỏ qua | Giữ 1000 |
| tags | Có mảng mới | Thay toàn bộ bằng ["work", "premium"] |
| stock | Bị bỏ qua | Giữ 5 |

Ví dụ này cho thấy một request có thể đồng thời giữ nguyên một số field, làm rỗng một field và thay toàn bộ một mảng.

## 6. Lưu ý khi tự viết Controller hoặc dùng DTO

Quy tắc của định dạng patch chỉ có tác dụng nếu tầng xử lý giữ được ý nghĩa của payload. Khi tự nhận request bằng DTO thông thường, hai trường hợp không gửi thuộc tính và gửi thuộc tính với null có thể cùng được ánh xạ thành giá trị Java null. Nếu sau đó copy toàn bộ DTO sang entity, code có thể xóa nhầm dữ liệu.

Khi cần phân biệt rõ, có thể đọc payload dưới dạng JsonNode và kiểm tra sự hiện diện của thuộc tính:

~~~java
if (!patch.has("description")) {
    // Không có thuộc tính: giữ nguyên giá trị hiện tại.
} else if (patch.get("description").isNull()) {
    // Có thuộc tính và giá trị là JSON null: xử lý yêu cầu làm rỗng.
    product.setDescription(null);
} else {
    // Có giá trị cụ thể: cập nhật theo giá trị được gửi.
    product.setDescription(patch.get("description").asText());
}
~~~

JsonNode.has("description") trả về true khi thuộc tính hiện diện, kể cả khi giá trị là JSON null. Không dùng hasNonNull để kiểm tra sự hiện diện nếu cần phân biệt hai trạng thái, vì phương thức đó trả về false khi giá trị là null.

Với DTO chuyên biệt, có thể dùng kiểu dữ liệu hỗ trợ trạng thái undefined/present/null, hoặc tự thiết kế cơ chế theo dõi thuộc tính nào thực sự có trong request. Chỉ dùng Optional<T> không đồng nghĩa tự động giải quyết được khác biệt giữa thuộc tính bị bỏ qua và thuộc tính được gửi null.

## 7. Trường hợp mảng là quan hệ giữa các entity

Trong Spring Data REST, một collection trong mô hình có thể là danh sách giá trị đơn giản hoặc quan hệ tới tài nguyên khác. Quan hệ thường được biểu diễn bằng association link trong HAL và có endpoint association riêng.

Vì vậy, đừng mặc định mọi mảng hiển thị trong JSON đều có thể được thay đổi như một thuộc tính List thông thường. Hãy xem link quan hệ mà Spring Data REST trả về và dùng đúng endpoint/phương thức association được API công bố để thêm, thay thế hoặc gỡ liên kết. Với quan hệ tới nhiều tài nguyên, việc gửi một danh sách mới có thể mang ý nghĩa thay toàn bộ tập liên kết nếu endpoint hỗ trợ thao tác đó.

## 8. Checklist trước khi gửi request cập nhật

1. Xác định request là PUT, JSON Merge Patch hay JSON Patch.
2. Gửi đúng Content-Type: application/merge-patch+json hoặc application/json-patch+json.
3. Với mỗi thuộc tính, xác định rõ: giữ nguyên, gán giá trị, hay xóa/làm rỗng.
4. Nếu gửi mảng bằng Merge Patch, xác nhận client có chủ đích thay toàn bộ danh sách.
5. Kiểm tra validation, nullable và quy tắc nghiệp vụ trước khi cho phép gán null.
6. Với DTO tự xử lý PATCH, giữ được sự khác biệt giữa thuộc tính không xuất hiện và thuộc tính có giá trị null.
7. Với quan hệ entity, thao tác qua association resource phù hợp.
8. Sau khi cập nhật, GET lại tài nguyên để xác nhận trạng thái đã lưu, đặc biệt là các field bị bỏ qua và các phần tử mảng.

Có thể kiểm thử tối thiểu bốn tình huống độc lập: bỏ qua field, gửi null, gửi mảng rỗng và gửi mảng mới có ít phần tử hơn mảng cũ. Kiểm tra kết quả GET sau mỗi request sẽ giúp phát hiện sớm trường hợp cập nhật ngoài ý muốn.


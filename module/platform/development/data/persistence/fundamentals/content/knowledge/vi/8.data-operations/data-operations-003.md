# Cập nhật một phần hoặc thay thế toàn bộ bản ghi

Một người dùng mở trang chỉnh sửa hồ sơ khách hàng. Ban đầu hồ sơ có tên hiển thị, email, số điện thoại và tùy chọn giao diện. Người dùng chỉ thay đổi số điện thoại. Ứng dụng nên gửi và lưu **riêng trường vừa đổi**, hay gửi **toàn bộ hồ sơ sau khi chỉnh sửa**?

Hai cách đều có thể đúng, nhưng chúng mang ngữ nghĩa khác nhau:

- **Cập nhật một phần (partial update):** chỉ những trường hoặc thao tác được chỉ định mới thay đổi; các trường không được nhắc tới giữ nguyên theo hợp đồng API và cơ chế lưu trữ.
- **Thay thế toàn bộ bản ghi (full replacement):** nội dung mới được xem là trạng thái thay thế của phần dữ liệu mà người gửi có quyền sở hữu. Trường bị bỏ qua phải có quy tắc xử lý rõ: bị loại bỏ, lấy mặc định, hoặc bị từ chối vì thiếu.
- **Lệnh nghiệp vụ (domain command):** một yêu cầu như “đặt thêm 2 vé” hoặc “trừ 1 đơn vị tồn kho” diễn tả phép biến đổi có điều kiện. Nó không nên bị đánh đồng với việc gán trực tiếp một số lượng mới từ client.

Bài học nằm trong chương **Thao tác dữ liệu** thuộc mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Trọng tâm là thiết kế cập nhật dữ liệu bền vững cho Java, từ hợp đồng API, lược đồ và truy vấn, tới transaction, kiểm soát đồng thời, lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng.

## 1. Hình dung sự khác nhau qua một bản ghi

Giả sử trạng thái hiện tại:

~~~json
{
  "id": "C88",
  "displayName": "Nguyễn An",
  "email": "an@example.org",
  "phone": "0901234567",
  "settings": {
    "theme": "light",
    "language": "vi"
  },
  "version": 7
}
~~~

Người dùng chỉ muốn xóa số điện thoại.

**Cập nhật một phần**, theo một hợp đồng mà giá trị null nghĩa là xóa trường:

~~~json
{
  "phone": null
}
~~~

Kết quả mong muốn: **displayName**, **email**, **settings** giữ nguyên; **phone** bị xóa hoặc chuyển về trạng thái null; **version** tăng theo quy tắc kiểm soát đồng thời.

**Thay thế toàn bộ phần hồ sơ có thể chỉnh sửa**, khi API yêu cầu cung cấp đủ mọi trường:

~~~json
{
  "displayName": "Nguyễn An",
  "email": "an@example.org",
  "phone": null,
  "settings": {
    "theme": "light",
    "language": "vi"
  }
}
~~~

Kết quả có thể tương tự, nhưng rủi ro khác nhau. Nếu client lưu một bản hồ sơ cũ và gửi lại toàn bộ, những thay đổi do phiên làm việc khác thực hiện có thể bị ghi đè nếu không có cơ chế kiểm soát phiên bản.

### Bảng so sánh nhanh

| Tiêu chí | Cập nhật một phần | Thay thế toàn bộ |
|---|---|---|
| Dữ liệu đầu vào | Những trường thay đổi hoặc danh sách thao tác | Trạng thái đầy đủ của phần được phép thay thế |
| Trường vắng mặt | Thường giữ nguyên | Phải được định nghĩa: bỏ/xóa, mặc định hoặc báo thiếu |
| Cập nhật trường độc lập | Phù hợp, giảm nhu cầu truyền lại dữ liệu cũ | Dễ ghi đè thay đổi từ bản sao cũ |
| Kiểm tra hợp lệ | Kiểm tra field được sửa và bất biến của trạng thái cuối | Kiểm tra toàn bộ trạng thái thay thế |
| Tranh chấp đồng thời | Vẫn có thể lost update, nhất là khi cùng sửa một field | Nguy cơ ghi đè nhiều field nếu thiếu điều kiện phiên bản |
| Payload | Thường nhỏ hơn | Thường lớn hơn |
| Truy cập DB | Có thể UPDATE một số cột hoặc phép thay đổi tại server | Có thể UPDATE tất cả cột được sở hữu hoặc replace document |
| Tiến hóa schema | Ít yêu cầu client cũ biết trường mới hơn | Client cũ có thể làm mất trường mới khi gửi bản thay thế cũ |
| Bất biến nghiệp vụ | Vẫn cần kiểm tra dữ liệu cuối cùng | Vẫn cần kiểm tra dữ liệu cuối cùng |

**Điểm cốt lõi:** “Cập nhật một phần” là ngữ nghĩa dữ liệu được phép thay đổi. Nó **không bảo đảm** rằng DB chỉ ghi vài byte trên đĩa. Ví dụ PostgreSQL dùng MVCC và thường tạo phiên bản hàng mới khi UPDATE, kể cả khi chỉ sửa một cột.

## 2. Phân biệt trường không có, null và giá trị rỗng

Đây là nguồn lỗi phổ biến nhất khi thiết kế PATCH:

~~~json
{}
~~~

~~~json
{"phone": null}
~~~

~~~json
{"phone": ""}
~~~

Ba payload có thể mang ba ý nghĩa khác nhau:

1. **Không có phone:** không đề nghị thay đổi số điện thoại.
2. **phone = null:** yêu cầu xóa/đặt trạng thái không có số điện thoại, nếu contract cho phép.
3. **phone = chuỗi rỗng:** cung cấp giá trị rỗng; ứng dụng có thể từ chối, giữ nguyên chuỗi rỗng hoặc chuẩn hóa thành null theo chính sách công khai.

Không thể dùng phép kiểm tra đơn giản “giá trị khác null thì cập nhật” để phân biệt trường vắng mặt và trường hiện diện với giá trị null. Tương tự, giá trị **false**, **0** và mảng rỗng **[]** có thể là giá trị hợp lệ cần lưu, không phải tín hiệu “không thay đổi”.

### Ví dụ thay đổi danh sách

Với **settings.languages = ["vi", "en"]**, cập nhật:

~~~json
{"settings": {"languages": []}}
~~~

có thể có nghĩa “xóa hết các ngôn ngữ đã chọn” hoặc “thay thế riêng mảng languages bằng mảng rỗng”, tùy kiểu patch. Nó không có nghĩa “bỏ qua vì mảng không có phần tử”.

Một hợp đồng PATCH tốt luôn nêu rõ cách diễn giải **vắng mặt / null / rỗng** và cách cập nhật object lồng nhau hoặc mảng. Nếu cần phân biệt **đặt JSON null** với **xóa thuộc tính**, kiểu patch phải hỗ trợ hai thao tác riêng.

## 3. Ngữ nghĩa HTTP: PUT và PATCH

HTTP cung cấp các phương thức có ý nghĩa phổ biến:

- **PUT:** yêu cầu tạo hoặc thay thế trạng thái của resource đích theo representation được gửi, trong phạm vi hợp đồng mà server công bố. Nó thường phù hợp khi client gửi **toàn bộ trạng thái có thể chỉnh sửa**.
- **PATCH:** gửi một tập hướng dẫn thay đổi đối với resource. Cách diễn giải phụ thuộc **Content-Type** của tài liệu patch.
- **POST:** thường dùng tạo tài nguyên hoặc thực hiện lệnh nghiệp vụ có ngữ nghĩa riêng. Không phải mọi phép tăng/giảm số lượng nên được biến thành PUT/PATCH một trường số.

**Không có quy tắc rằng cứ PATCH là an toàn với race condition và cứ PUT là nguy hiểm.** Mỗi request vẫn cần điều kiện phiên bản, transaction và validation khi nghiệp vụ yêu cầu.

### Idempotency

Một phương thức được xem là **idempotent** khi gửi cùng yêu cầu nhiều lần có **hiệu ứng mong muốn lên trạng thái tài nguyên tương đương** với gửi một lần. PUT được định nghĩa có tính idempotent ở mức ngữ nghĩa HTTP; PATCH có thể idempotent hoặc không, tùy thao tác.

~~~text
PUT /profiles/C88
Body: trạng thái hồ sơ đã chỉnh sửa
=> Gửi lại cùng representation thường vẫn nhằm cùng trạng thái.

PATCH /profiles/C88
Body: đặt phone = "090..."
=> Gửi lại có thể vẫn tạo cùng giá trị phone.

PATCH /counters/A
Body: tăng 1
=> Gửi hai lần sẽ tăng 2 nếu không có chống lặp.
~~~

Một lần cập nhật có thể vẫn làm thay đổi metadata như thời điểm sửa hoặc phiên bản nội bộ; khi thiết kế retry, cần xét hiệu ứng thực tế của service. **Idempotent về giá trị cuối** không có nghĩa mọi request được gửi lại đều thành công: nếu dùng điều kiện phiên bản, lần gửi lại có thể nhận lỗi do phiên bản cũ.

### Không đồng nhất HTTP verb với lệnh SQL

Một API PUT có thể dùng câu SQL UPDATE để thực hiện thay thế logic; API PATCH cũng có thể phải đọc bản ghi, kiểm tra và ghi lại nhiều cột trong một transaction. Tên HTTP method không quy định cấu trúc vật lý của DB.

## 4. Hai định dạng PATCH thường gặp

### JSON Merge Patch

Theo ngữ nghĩa **application/merge-patch+json**, một object patch cập nhật các thuộc tính được nhắc tới; thuộc tính **null** thường có ý nghĩa *xóa thuộc tính*; các thuộc tính vắng mặt giữ nguyên. Một object lồng nhau được xử lý đệ quy theo quy tắc merge; **mảng được thay như một giá trị**, không tự ghép từng phần tử.

Trạng thái:

~~~json
{
  "displayName": "Nguyễn An",
  "phone": "0901234567",
  "settings": {"theme": "light", "language": "vi"}
}
~~~

Merge patch:

~~~json
{
  "phone": null,
  "settings": {"theme": "dark"}
}
~~~

Kết quả logic:

~~~json
{
  "displayName": "Nguyễn An",
  "settings": {"theme": "dark", "language": "vi"}
}
~~~

Nếu cần lưu một thuộc tính JSON có giá trị **null** thật sự và phân biệt nó với thuộc tính không tồn tại, JSON Merge Patch không phù hợp trực tiếp cho trường hợp đó vì null mang ý nghĩa xóa. Cần chọn định dạng patch khác hoặc quy ước API khác được định nghĩa rõ.

### JSON Patch

Theo **application/json-patch+json**, request chứa danh sách thao tác có thứ tự, ví dụ **add**, **remove**, **replace**, **move**, **copy**, **test**.

~~~json
[
  {"op": "test", "path": "/settings/theme", "value": "light"},
  {"op": "replace", "path": "/settings/theme", "value": "dark"},
  {"op": "remove", "path": "/phone"}
]
~~~

**test** có thể kiểm tra điều kiện trước khi đổi; **remove** diễn đạt xóa một cách tường minh. Đường dẫn theo **JSON Pointer**; khi chứa ký tự đặc biệt phải được escape theo quy tắc của định dạng (ví dụ dấu **~** và **/**). Mọi thao tác phải tuân theo thứ tự; nếu một thao tác lỗi, hệ thống cần xử lý sao cho không để resource bị áp dụng dở dang trái với hợp đồng. Khi persistence ở nhiều bản ghi hoặc dịch vụ, phải tự tổ chức transaction hoặc cơ chế nhất quán thích hợp.

JSON Patch có thể thay phần tử mảng theo vị trí, nhưng vị trí có thể thay đổi giữa hai lần đọc. Nếu dựa vào index mảng, cần kiểm tra phiên bản hoặc điều kiện trước khi cập nhật để tránh sửa nhầm phần tử.

**Ví dụ không phải JSON Patch:** request tự chế như **{"increment": 1}** có thể là một API domain command hợp lệ, nhưng không được gọi là JSON Patch tiêu chuẩn chỉ vì sử dụng HTTP PATCH.

## 5. Xác định phạm vi “toàn bộ” của replacement

Một câu hỏi khó: **thay thế toàn bộ bản ghi là toàn bộ phần nào?** Trong DB một bản ghi có thể gồm:

- **ID, tenant ID**: định danh và phạm vi bảo mật.
- **created_at, created_by**: metadata được server quản lý.
- **version, updated_at**: metadata kiểm soát đồng thời.
- **display_name, phone, settings**: phần client có thể chỉnh sửa.
- **status, credit_limit**: trường chỉ lệnh nghiệp vụ hoặc người có quyền đặc biệt mới được đổi.

Không nên cho một request PUT của người dùng thay thế tùy ý **id**, **tenant_id**, **created_at** hay các trường mà họ không có quyền sửa. Một hợp đồng thường xác định “representation đầy đủ của **phần hồ sơ người dùng có quyền chỉnh sửa**” rồi để server bảo tồn các trường thuộc trách nhiệm của server.

Nếu API nhận thiếu một trường bắt buộc trong phần được thay thế, nên **từ chối bằng lỗi validation** hoặc có quy tắc mặc định nhất quán; đừng âm thầm giữ một giá trị cũ nếu hợp đồng tuyên bố đây là thay thế toàn bộ.

Ví dụ: biểu diễn PUT đầy đủ của phần hồ sơ:

~~~json
{
  "displayName": "Nguyễn An",
  "email": "an@example.org",
  "phone": null,
  "settings": {"theme": "dark", "language": "vi"}
}
~~~

Không có **id**, **tenantId**, **version** bên trong payload vì chúng được quản lý qua đường dẫn, ngữ cảnh xác thực và điều kiện sửa (ví dụ If-Match). Đây là **một thiết kế hợp đồng**, không phải yêu cầu bắt buộc cho mọi API.

## 6. Cơ sở dữ liệu quan hệ: cập nhật cột cụ thể

Giả sử hệ thống quản lý hồ sơ khách hàng theo tenant bằng PostgreSQL:

~~~sql
CREATE TABLE customer_profiles (
    tenant_id UUID NOT NULL,
    id UUID NOT NULL,
    display_name TEXT NOT NULL
        CHECK (length(btrim(display_name)) BETWEEN 1 AND 120),
    email TEXT NOT NULL,
    phone TEXT,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(settings) = 'object'),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    CONSTRAINT uq_profile_email_in_tenant UNIQUE (tenant_id, email)
);
~~~

Schema này bảo vệ ID, tenant, tên không rỗng, hình dạng cơ bản của settings và email duy nhất trong tenant. Việc email đã được chuẩn hóa, xác minh hay được cấp quyền sửa vẫn cần quy tắc ở ứng dụng và/hoặc constraint bổ sung.

### Cập nhật một trường

~~~sql
UPDATE customer_profiles
SET phone = $3,
    version = version + 1,
    updated_at = now()
WHERE tenant_id = $1
  AND id = $2
  AND version = $4
RETURNING version;
~~~

Trong ví dụ này:

- **$1, $2** xác định bản ghi trong tenant đúng.
- **$3** có thể là giá trị điện thoại mới hoặc SQL NULL nếu muốn xóa số điện thoại.
- **$4** là phiên bản client đã đọc.
- **RETURNING version** cung cấp phiên bản mới khi cập nhật thành công.
- Không có hàng nào được trả về nghĩa là **bản ghi không tồn tại trong phạm vi đó hoặc phiên bản không còn khớp**; không nên tự khẳng định một nguyên nhân khi chưa kiểm tra.

Ở PostgreSQL, UPDATE một cột thường vẫn tạo phiên bản hàng mới do MVCC và có thể ảnh hưởng đến chỉ mục/WAL tùy cách hệ thống thực thi. Lợi ích chính của câu lệnh này là **ngữ nghĩa chỉ thay phone** và giảm rủi ro ghi đè trường khác, không phải cam kết ghi vật lý đúng số byte của phone.

### Thay thế toàn bộ nhóm trường có thể chỉnh sửa

~~~sql
UPDATE customer_profiles
SET display_name = $3,
    email = $4,
    phone = $5,
    settings = $6::jsonb,
    version = version + 1,
    updated_at = now()
WHERE tenant_id = $1
  AND id = $2
  AND version = $7
RETURNING version;
~~~

Ứng dụng phải tạo đủ **display_name**, **email**, **phone**, **settings** theo hợp đồng. Những trường server quản lý như **id**, **tenant_id**, **created_at** không bị thay thế. DB vẫn kiểm tra **CHECK**, **NOT NULL**, **UNIQUE**. Nếu email mới trùng, giao dịch ghi bị từ chối và bản ghi cũ không bị thay thế một phần do câu UPDATE này.

### JSONB lồng nhau: thay thuộc tính hay thay object?

Khi chỉ muốn đổi **settings.theme**, có thể dùng:

~~~sql
UPDATE customer_profiles
SET settings = jsonb_set(settings, '{theme}', to_jsonb($3::text), true),
    version = version + 1,
    updated_at = now()
WHERE tenant_id = $1 AND id = $2 AND version = $4
RETURNING version;
~~~

Câu lệnh chỉ thay thuộc tính **theme** ở cấp cao nhất của JSON object; các thuộc tính còn lại như **language** giữ nguyên. Với đường dẫn lồng sâu, **jsonb_set** không tự tạo mọi object cha còn thiếu: cần thiết kế xử lý khi cấu trúc trung gian không tồn tại.

Nếu muốn loại thuộc tính thay vì gán một giá trị null:

~~~sql
UPDATE customer_profiles
SET settings = settings - 'theme',
    version = version + 1,
    updated_at = now()
WHERE tenant_id = $1 AND id = $2 AND version = $3
RETURNING version;
~~~

Toán tử **-** trong ví dụ dùng cho khóa ở cấp cao nhất của JSONB. **JSON null**, **SQL NULL** và **khóa JSON không tồn tại** là ba trạng thái cần phân biệt cẩn thận trong serialization, câu truy vấn và API.

## 7. Cập nhật tương đối và lệnh nghiệp vụ

Một số yêu cầu là **phép biến đổi**, không phải gán một giá trị mới. Ví dụ hàng tồn kho:

~~~text
Hiện có 5 sản phẩm.
Đơn A mua 3.
Đơn B mua 3 cùng lúc.
~~~

Nếu mỗi request đọc **available = 5** rồi gửi **available = 2**, hệ thống có thể ghi sai vì cả hai dựa vào trạng thái cũ.

Một lệnh cập nhật tại nơi lưu an toàn hơn:

~~~sql
UPDATE inventory
SET available = available - $3
WHERE tenant_id = $1
  AND product_id = $2
  AND $3 > 0
  AND available >= $3
RETURNING available;
~~~

Chỉ khi trả về một hàng thì việc trừ số lượng mới được thực hiện. PostgreSQL phối hợp các UPDATE đồng thời trên cùng hàng theo cơ chế lock/MVCC; điều kiện được kiểm tra theo mức isolation thực tế. Cần lưu trữ idempotency key hoặc định danh lệnh nếu khách hàng có thể retry sau timeout để tránh trừ hàng hai lần.

**Không nên cho phép client PATCH trực tiếp available = 2** khi yêu cầu thật sự là “mua 3 sản phẩm”. Số lượng còn lại là trạng thái do nghiệp vụ và cơ sở dữ liệu quản lý; lệnh mua cần xác thực, kiểm tra quyền, tồn kho và transaction cùng các thay đổi đơn hàng.

## 8. Document database: replace và update là hai thao tác khác nhau

Ở một document database như MongoDB, cùng một ý tưởng biểu diễn khá trực tiếp.

Document hiện tại:

~~~json
{
  "_id": "C88",
  "tenantId": "T42",
  "displayName": "Nguyễn An",
  "phone": "0901234567",
  "settings": {"theme": "light", "language": "vi"},
  "version": 7
}
~~~

**Cập nhật một phần** bằng toán tử của MongoDB:

~~~javascript
db.profiles.updateOne(
  { _id: "C88", tenantId: "T42", version: 7 },
  {
    $set: { "settings.theme": "dark" },
    $unset: { phone: "" },
    $inc: { version: 1 }
  }
);
~~~

Tại mức document, thao tác update thường được thực hiện nguyên tử theo bảo đảm của backend. Kết quả **matchedCount = 0** cho thấy khóa/tenant/version không khớp, không đủ để phân biệt mất bản ghi với conflict nếu chưa kiểm tra thêm.

**Thay thế toàn bộ document** bằng **replaceOne**:

~~~javascript
db.profiles.replaceOne(
  { _id: "C88", tenantId: "T42", version: 7 },
  {
    _id: "C88",
    tenantId: "T42",
    displayName: "Nguyễn An",
    phone: null,
    settings: { theme: "dark", language: "vi" },
    version: 8
  }
);
~~~

Các trường có trong document cũ nhưng **không có trong replacement** sẽ không được giữ như trước, trừ những quy tắc đặc biệt của backend (ví dụ định danh bất biến). Trong ví dụ này không có tùy chọn **upsert**, vì nghiệp vụ đang sửa hồ sơ đã tồn tại chứ không chủ đích tạo hồ sơ mới khi key không khớp.

Đoạn MongoDB là ví dụ riêng của công nghệ này: không suy ra rằng mọi document database đều dùng đúng các toán tử, hay mọi thao tác nhiều document đều nguyên tử. Nếu cần cập nhật các document liên quan, phải kiểm tra khả năng transaction và mức consistency của backend.

### Vì sao replacement dễ làm mất trường mới?

Giả sử server đã bổ sung **marketingConsent** vào document, nhưng client cũ chỉ biết ba trường trước đây. Nếu client cũ thực hiện replaceOne với cấu trúc cũ, nó có thể **xóa marketingConsent**. Cập nhật riêng **phone** bằng $set sẽ không đụng vào trường mới.

Đó là một trong các lý do API thường tách rõ những trường client sở hữu và những trường server quản lý, đồng thời dùng version hoặc chiến lược tương thích trong quá trình nâng cấp.

## 9. Lost update và kiểm soát đồng thời

Vấn đề không chỉ nằm ở PUT hay PATCH; nó nằm ở việc hai tác vụ cùng ghi dựa trên trạng thái nào.

~~~text
Bản ghi ban đầu version=10:
displayName="An", phone="0901"

Thời điểm   Client A                       Client B
t1          GET version=10                GET version=10
t2          Sửa phone="0902"              Sửa displayName="An Nguyen"
t3          PUT toàn bộ version=10        -
t4          -                              PUT toàn bộ dữ liệu cũ version=10

Nếu không kiểm tra version:
  bản ghi cuối có thể displayName="An Nguyen", phone="0901".
  Thay đổi phone của A đã bị mất.
~~~

### Optimistic locking bằng version

Mỗi lần ghi thành công, phiên bản tăng. Câu UPDATE kiểm tra **version = phiên bản đã đọc**. Với lịch trình trên:

1. A cập nhật từ version 10 sang 11 thành công.
2. B gửi update có điều kiện version 10.
3. DB trả về **0 hàng cập nhật** do phiên bản đã khác.
4. B đọc trạng thái mới và quyết định hợp nhất hoặc báo conflict.

Đối với API HTTP, server có thể xuất **ETag** đại diện phiên bản resource và yêu cầu header **If-Match** từ client. Khi điều kiện không đạt, phản hồi điển hình là **412 Precondition Failed**; nếu API báo conflict không dùng precondition, **409 Conflict** có thể phù hợp theo hợp đồng. Cần phân biệt **404/403** và **mismatch phiên bản** mà không rò rỉ sự tồn tại của dữ liệu khác tenant.

**Tránh giả định “version luôn đủ”:** nếu một transaction cập nhật nhiều bảng, phải đảm bảo tất cả thao tác cần thiết nằm trong cùng transaction hoặc cơ chế phối hợp phù hợp. Việc tăng version trên một hàng không tự bảo vệ toàn bộ hệ thống khỏi write skew hoặc lỗi ở service bên ngoài.

### PATCH trên các trường khác nhau có phải xung đột?

Nếu A chỉ UPDATE phone còn B chỉ UPDATE display_name, DB có thể áp dụng cả hai mà không mất thay đổi ở các cột còn lại. Tuy nhiên:

- Nếu cả hai sửa **cùng field**, vẫn cần quyết định ai thắng.
- Nếu có **bất biến liên trường** (ví dụ ngày bắt đầu phải trước ngày kết thúc), hai patch trên hai field khác nhau có thể khiến trạng thái cuối không hợp lệ nếu thiếu validation/transaction.
- Nếu ứng dụng đòi toàn bộ hồ sơ được sửa theo một phiên bản nhất quán, optimistic locking toàn bản ghi có thể là lựa chọn đúng dù nhiều xung đột hơn.
- Nếu cho cập nhật độc lập, có thể dùng thao tác field-level an toàn, nhưng phải quy định rõ ranh giới aggregate và các bất biến cần bảo vệ.

Không chọn cách “chấp nhận mọi PATCH vì chỉ sửa một trường” mà bỏ qua kiểm soát đồng thời.

## 10. Java: biểu diễn rõ ba trạng thái cho một field

Một DTO Java thông thường với trường **String phone** có thể biến cả “không gửi phone” lẫn “phone: null” thành cùng giá trị **null** sau khi bind JSON. Vì vậy cần cấu trúc giữ cả **trường có được cung cấp hay không**.

Một kiểu nhỏ bằng Java 17:

~~~java
record FieldPatch<T>(boolean supplied, T value) {
    static <T> FieldPatch<T> omitted() {
        return new FieldPatch<>(false, null);
    }

    static <T> FieldPatch<T> provided(T value) {
        return new FieldPatch<>(true, value);
    }
}

record ProfilePatch(
    FieldPatch<String> displayName,
    FieldPatch<String> phone
) {}
~~~

Ba trạng thái:

~~~java
FieldPatch<String> a = FieldPatch.omitted();      // Không đổi
FieldPatch<String> b = FieldPatch.provided(null); // Xóa/clear nếu cho phép
FieldPatch<String> c = FieldPatch.provided("0902"); // Đặt giá trị mới
~~~

Tầng HTTP phải chủ động parse JSON để điền đúng **supplied**. Ví dụ với Jackson **JsonNode**:

~~~java
import com.fasterxml.jackson.databind.JsonNode;

static FieldPatch<String> parsePhone(JsonNode request) {
    JsonNode node = request.get("phone");
    if (node == null) {
        return FieldPatch.omitted();           // Property vắng mặt
    }
    if (node.isNull()) {
        return FieldPatch.provided(null);     // JSON null
    }
    if (!node.isTextual()) {
        throw new IllegalArgumentException("phone must be a string or null");
    }
    return FieldPatch.provided(node.textValue());
}
~~~

Đây là mô tả một phần của lớp parsing, **chưa phải triển khai HTTP hoàn chỉnh**. Một endpoint thực tế phải giới hạn danh sách field được thay đổi, từ chối payload lạ nếu hợp đồng yêu cầu và chạy validation trên trạng thái cuối cùng. Kiểm tra **null** cho **displayName** phải khác **phone**, vì schema không cho display_name là NULL.

### Không mất thông tin khi map DTO

Ví dụ sai thường gặp:

~~~java
if (request.phone() != null) {
    entity.setPhone(request.phone());
}
~~~

Nếu user cố ý xóa phone bằng JSON null, nhánh này sẽ bỏ qua. Một lỗi khác là copy mọi property của DTO vào entity mà không phân biệt field vắng mặt: các giá trị không được gửi có thể bị ghi đè thành null. Khi dùng reflection mapper hoặc BeanUtils, cần hiểu chính xác cách mapper xử lý null và missing.

## 11. Java JDBC: partial update có điều kiện theo version

Ví dụ repository thay số điện thoại trong PostgreSQL. **null** được phép với phone, nhưng không được phép với display_name theo schema:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.OptionalLong;
import java.util.UUID;
import javax.sql.DataSource;

final class JdbcProfileRepository {
    private final DataSource dataSource;

    JdbcProfileRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    OptionalLong setPhone(
            UUID tenantId, UUID profileId, long expectedVersion, String phone)
            throws SQLException {
        if (tenantId == null || profileId == null || expectedVersion < 0) {
            throw new IllegalArgumentException("invalid identity or version");
        }

        String sql = """
            UPDATE customer_profiles
               SET phone = ?,
                   version = version + 1,
                   updated_at = now()
             WHERE tenant_id = ? AND id = ? AND version = ?
             RETURNING version
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            if (phone == null) {
                statement.setNull(1, Types.VARCHAR);
            } else {
                statement.setString(1, phone);
            }
            statement.setObject(2, tenantId);
            statement.setObject(3, profileId);
            statement.setLong(4, expectedVersion);

            try (ResultSet rows = statement.executeQuery()) {
                return rows.next()
                    ? OptionalLong.of(rows.getLong("version"))
                    : OptionalLong.empty();
            }
        }
    }
}
~~~

**Ý nghĩa:** phương thức này đã thể hiện lệnh “đặt phone thành giá trị X” nên nó được gọi **chỉ khi client thực sự cung cấp field phone**. Nếu field vắng mặt, service không nên tự gọi **setPhone(..., null)**. Đầu vào bắt buộc được lấy tenant từ ngữ cảnh xác thực đáng tin cậy. Trong ví dụ này, một câu UPDATE là một thao tác nguyên tử tại DB; khi có nhiều thao tác cùng cần commit, đặt chúng trong transaction đúng ranh giới nghiệp vụ.

**OptionalLong.empty()** không có nghĩa chắc chắn bản ghi không tồn tại: cũng có thể phiên bản không khớp. Service cần quyết định mapping theo API và chính sách tránh tiết lộ dữ liệu của tenant khác.

### Full replacement trong Java

Với PUT, DTO nên yêu cầu đủ những trường client sở hữu:

~~~java
record ReplaceProfile(
    String displayName,
    String email,
    String phone,
    String settingsJson
) {
    ReplaceProfile {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("displayName required");
        }
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("email required");
        }
        if (settingsJson == null) {
            throw new IllegalArgumentException("settings required");
        }
    }
}
~~~

Sau đó repository dùng câu UPDATE thay thế nhóm field như mục 6 cùng điều kiện **WHERE ... version = expectedVersion**. Trong ứng dụng thật, cần parse và validate **settings** thành cấu trúc dữ liệu được phép, chuẩn hóa email và kiểm tra quyền đối với field, không chỉ chấp nhận một JSON string bất kỳ.

Nếu sử dụng ORM/JPA, việc sửa một object đã load và gọi save có thể sinh SQL UPDATE của nhiều cột tùy dirty checking và cấu hình ORM. Cần xem SQL thực tế, version field (ví dụ cơ chế optimistic locking tương ứng), cách merge detached entity và transaction. Một detached DTO cũ không nên được merge như một entity đầy đủ khi yêu cầu chỉ sửa một field.

## 12. Lỗi, retry và tính bền vững

Các kết quả ghi cần được phân loại rõ:

| Tình huống | Cách xử lý |
|---|---|
| Field không hợp lệ hoặc thiếu trong PUT | Trả lỗi validation có thông tin trường |
| PATCH thay field không có quyền | Từ chối theo chính sách authorization/field allowlist |
| Vi phạm NOT NULL, CHECK, UNIQUE, FK | DB từ chối; ánh xạ lỗi constraint sang lỗi nghiệp vụ hoặc lỗi triển khai thích hợp |
| Phiên bản cũ, UPDATE không khớp | Conflict/precondition failed theo contract; có thể đọc lại để hợp nhất |
| Bản ghi không tồn tại trong tenant | Phản hồi phù hợp 404 hoặc chính sách bảo mật |
| SQL timeout hoặc mất kết nối khi ghi | Có thể chưa biết thao tác đã commit hay chưa |
| Lỗi deadlock hoặc serialization | Có thể retry toàn transaction có giới hạn nếu thao tác và backend cho phép |

Một lần client nhận timeout **không khẳng định server chưa ghi**. Nếu gửi lại PUT có điều kiện phiên bản cũ, server có thể trả precondition failed vì lần trước đã ghi thành công. Cần cách truy xuất lại trạng thái hoặc lưu **idempotency key** cho lệnh tạo tác động nghiệp vụ. Với PATCH dạng tăng/giảm, việc retry không kiểm soát có thể lặp tác động.

Với PostgreSQL, một số SQLSTATE đáng biết: **23505** (unique violation), **23502** (not-null violation), **23514** (check violation), **40001** (serialization failure) và **40P01** (deadlock detected). Không nên trả raw database exception chứa giá trị nhạy cảm cho người dùng. Cần log request ID, tenant trong phạm vi cho phép, constraint name và thời điểm lỗi để chẩn đoán.

### Transaction nhiều bản ghi

Giả sử cập nhật thông tin giao hàng đồng thời cập nhật lịch sử thay đổi. Nếu yêu cầu “hai bước cùng thành công hoặc cùng thất bại”, nên đặt UPDATE và INSERT lịch sử trong **một transaction** nếu cùng DB hỗ trợ:

~~~sql
BEGIN;

UPDATE customer_profiles
SET phone = $3,
    version = version + 1,
    updated_at = now()
WHERE tenant_id = $1 AND id = $2 AND version = $4
RETURNING version;

-- Chỉ ghi audit log nếu UPDATE đã sửa đúng một hàng.
INSERT INTO profile_change_log
    (tenant_id, profile_id, changed_field, changed_at)
VALUES ($1, $2, 'phone', now());

COMMIT;
~~~

Đây là **phác thảo trình tự**, chưa phải script có điều kiện đầy đủ: ứng dụng phải kiểm tra kết quả UPDATE trước khi INSERT; nếu UPDATE không khớp, rollback. Cấu trúc bảng log cần được tạo và quản lý riêng trong một hệ thống thật. Nếu log nằm ở dịch vụ khác, DB transaction không tự bao trùm được nó; có thể dùng **transactional outbox** cùng luồng phát sự kiện đáng tin cậy.

## 13. Bảo mật và quyền cập nhật theo trường

Một PATCH nhỏ chưa chắc an toàn hơn PUT. Nếu endpoint chấp nhận mọi field trong JSON và tự ánh xạ vào entity, người dùng có thể cố gắng thay **tenantId**, **role**, **accountStatus** hoặc **creditLimit** dù UI không hiển thị những trường đó. Đây là dạng rủi ro **mass assignment / over-posting**.

Cần thiết kế rõ:

- **Field allowlist** cho từng command/endpoint; chỉ những trường công bố mới có thể cập nhật.
- **Authentication và authorization** trước khi truy cập bản ghi, lấy tenant từ ngữ cảnh tin cậy.
- **Ràng buộc tại DB** cho các bất biến cốt lõi, ví dụ UNIQUE theo tenant, FK ghép tenant, CHECK và NOT NULL.
- **Truy vấn có tham số**; không ghép giá trị JSON vào SQL string hoặc dùng tên cột tùy ý từ client.
- **Kiểm soát dữ liệu nhạy cảm** trong audit log, message, snapshot và bản sao lưu; patch document có thể chứa thông tin cá nhân.
- **ETag và cache**: chỉ dùng validator phù hợp với representation; thông tin version không phải bí mật thay thế quyền truy cập.

Khi dữ liệu được chia sẻ qua nhiều endpoint, nên thiết kế một ranh giới nghiệp vụ thống nhất cho việc thay đổi trạng thái để tránh “endpoint A cấm sửa, endpoint B vẫn ghi được”.

## 14. Tiến hóa schema và tương thích với client cũ

Giả sử phiên bản 1 của hồ sơ có **displayName**, **email**, **phone**. Phiên bản 2 bổ sung **preferredLanguage**.

**Với partial update:** client cũ gửi **{"phone": "0902"}**, trường **preferredLanguage** có thể được giữ nguyên mà không cần client biết đến nó.

**Với full replacement:** client cũ không gửi **preferredLanguage**. Nếu server xem thiếu nghĩa là xóa hoặc đặt mặc định, một trường mới có thể bị mất. Có một số chiến lược:

1. **Version hợp đồng API:** client và server thống nhất cấu trúc đầy đủ theo phiên bản; ngăn client cũ vô tình phá dữ liệu mới.
2. **Tách field server sở hữu:** không đưa field mới vào phạm vi replacement của client cũ; công bố rõ ranh giới.
3. **Từ chối representation thiếu** khi cần toàn bộ trạng thái; hướng client cập nhật.
4. **Cơ chế chuyển đổi schema có kiểm soát:** đọc phiên bản cũ, áp quy tắc chuyển đổi, nhưng không tự đoán dữ liệu nghiệp vụ chưa có.
5. **Chuyển sang patch cho use case sửa từng trường**, khi nghiệp vụ không cần client thay thế toàn bộ.

### Migration dữ liệu cũ

Khi bổ sung **NOT NULL** hoặc đổi kiểu cột, cần kiểm kê dữ liệu hiện hữu, backfill, triển khai nhiều phiên bản tương thích và xác minh constraint. Không gán một giá trị mặc định chỉ để migration chạy được nếu nó làm sai nghĩa lịch sử.

Với document database, reader có thể cần hỗ trợ nhiều **schemaVersion** và writer cần ghi định dạng mới. Một lần replace toàn document từ client cũ có thể đưa cấu trúc cũ trở lại; cần kiểm soát version và đường ghi của các ứng dụng liên quan.

## 15. Hiệu năng: đo theo đường cập nhật thực tế

Thay vì kết luận “PATCH luôn nhanh hơn PUT”, hãy xem các chi phí chính:

| Yếu tố | Partial update | Full replacement |
|---|---|---|
| Payload qua mạng | Có thể rất nhỏ | Thường gửi nhiều trường hơn |
| Serialization / parse | Xử lý subset và logic merge | Parse representation đầy đủ |
| DB write | Có thể tránh tác động cột không liên quan | Có thể ảnh hưởng thêm index/WAL/replication |
| Read trước write | Có thể không cần nếu thao tác SQL đủ điều kiện | Có thể không cần nếu có đủ payload và version |
| Kiểm tra invariants | Có thể phải đọc trạng thái cuối sau merge | Thường kiểm tra trực tiếp trạng thái mới |
| Xung đột | Tùy version guard, thao tác atomic và phạm vi field | Thường dễ ghi đè nếu dùng snapshot cũ |
| Số request | Một patch có thể gộp nhiều thay đổi; nhiều patch nhỏ gây nhiều round trip | Có thể thay toàn bộ bằng một request |
| Cache / projection | Cần làm mới dữ liệu phụ thuộc đúng cách | Cũng cần làm mới dữ liệu phụ thuộc |

Ở PostgreSQL, MVCC và HOT update (khi đủ điều kiện) làm chi phí phụ thuộc cột nào được sửa, chỉ mục, kích thước hàng và còn không gian trên trang hay không. Ở document store, ghi một đường dẫn lồng nhau **không đảm bảo** động cơ lưu trữ chỉ sửa vài byte vật lý.

Các chỉ số nên đo: **p50/p95/p99 latency của PUT/PATCH**, kích thước request, số query/round trip, số conflict phiên bản, tỷ lệ retry, số timeout, WAL/replication lag, CPU của validation và dung lượng/index của những trường thường đổi. Kiểm thử với **tỷ lệ đọc/ghi và kích thước bản ghi gần thực tế**.

## 16. Lựa chọn chiến lược theo tình huống

| Nhu cầu | Hướng thiết kế |
|---|---|
| Người dùng chỉ đổi số điện thoại | PATCH field phone; phân biệt omitted và null |
| Form chỉnh sửa toàn bộ nhóm cấu hình thuộc user | PUT phần cấu hình đầy đủ, có validation và If-Match/version |
| Trừ một đơn vị tồn kho | Command nghiệp vụ + UPDATE có điều kiện tại DB + idempotency |
| Sửa địa chỉ giao hàng đã có nhiều dữ liệu con | Chọn PATCH hay replacement theo ownership và phạm vi atomicity |
| Thay toàn bộ tài liệu trong document store | replace có version guard; bảo vệ field server sở hữu |
| Đổi một thuộc tính JSONB | jsonb_set hoặc toán tử tương ứng; không ghi đè object ngoài ý muốn |
| Cập nhật nhiều bảng phải nhất quán | Transaction với điều kiện ghi và xử lý lỗi phù hợp |
| Client cũ chưa biết field mới | Kiểm soát full replacement bằng version/schema hoặc dùng patch phù hợp |

Một quy trình ra quyết định có thể bắt đầu từ câu hỏi: **người dùng muốn thay một giá trị, thay một phần tài nguyên do họ sở hữu hay thực hiện một phép biến đổi nghiệp vụ?** Từ đó chọn representation và cơ chế lưu trữ, rồi thiết kế concurrency control phù hợp.

## 17. Bài thực hành: sửa hồ sơ khách hàng trong hệ thống Java

Một dịch vụ Java phục vụ nhiều tenant lưu hồ sơ với **id**, **tenantId**, **displayName**, **email**, **phone**, **settings** và **version**. Người dùng được đổi tên, điện thoại và một số tùy chọn; email cần quy trình xác minh riêng. Hai thiết bị có thể mở cùng hồ sơ và gửi cập nhật gần như đồng thời.

**Yêu cầu thiết kế:**

1. Định nghĩa contract PATCH cho **displayName**, **phone**, **settings.theme**; diễn giải rõ **missing**, **null**, chuỗi rỗng và mảng rỗng.
2. Định nghĩa contract PUT cho toàn bộ nhóm field mà người dùng được thay thế; quyết định cách xử lý field bắt buộc bị bỏ qua và field do server sở hữu.
3. Viết câu PostgreSQL UPDATE chỉ thay phone cùng điều kiện **version**, trả về version mới.
4. Viết câu UPDATE thay toàn bộ nhóm field client sở hữu; chứng minh rằng **id** và **tenantId** không bị thay.
5. Minh họa hai thiết bị cùng đọc version 7 và cập nhật; phân tích lost update khi thiếu version guard, và kết quả khi có.
6. Thiết kế parsing DTO Java phân biệt field không gửi và field JSON null.
7. Với yêu cầu “cộng 1 điểm thưởng”, giải thích vì sao gửi giá trị mới lấy từ bản sao cũ dễ sai; đề xuất lệnh cập nhật nguyên tử và xử lý retry.
8. Xác định field allowlist và phân quyền; kiểm tra tenant trước khi ghi.
9. Lập kế hoạch nâng schema thêm trường **preferredLanguage** mà client cũ vẫn dùng được.
10. Đề xuất kiểm thử tích hợp/concurrency và các chỉ số cần theo dõi trong production.

**Gợi ý giải:** dùng PATCH cho thao tác đặt/xóa từng field với mô hình ba trạng thái, còn PUT yêu cầu đủ toàn bộ nhóm thuộc quyền chỉnh sửa. Đặt điều kiện **WHERE tenant_id = ? AND id = ? AND version = ?** và tăng version khi ghi thành công. Không cho phép sửa ID, tenant hay email chưa qua quy trình riêng. Các lệnh tăng/giảm điểm hoặc tồn kho nên là phép cập nhật nguyên tử có điều kiện, kèm idempotency khi có khả năng retry. Trường mới cần được bảo vệ khỏi replacement từ client cũ qua hợp đồng có version hoặc phạm vi sở hữu rõ ràng.

### Câu hỏi tự kiểm tra

- **Trường vắng mặt**, **trường bằng null** và **trường là chuỗi rỗng** khác nhau thế nào khi PATCH?
- Vì sao một lệnh SQL UPDATE chỉ sửa một cột vẫn có thể tạo phiên bản hàng mới ở PostgreSQL?
- Khi PUT đầy đủ nhưng payload thiếu field server mới thêm, nguy cơ gì xuất hiện?
- Vì sao hai PATCH vào hai trường khác nhau không tự bảo đảm an toàn cho mọi bất biến nghiệp vụ?
- Khi UPDATE ... WHERE version = ? không trả về hàng nào, có thể kết luận chính xác nguyên nhân chưa?
- Tại sao phép “trừ 1 đơn vị tồn kho” không nên được hiện thực bằng cách gửi một giá trị available cố định?
- Một PATCH đặt phone về null có thể bị mất tác dụng thế nào khi dùng DTO Java thông thường?
- Nếu commit bị timeout, vì sao không nên lập tức gửi lại một phép tăng số?
- PUT có thể là idempotent về trạng thái đích mà lần retry với If-Match vẫn nhận lỗi không?
- Khi nào dùng snapshot đầy đủ, khi nào dùng patch, và bất biến nào phải được kiểm tra tại nơi lưu?

Kết thúc bài học, người học phải diễn đạt được ngữ nghĩa của **cập nhật một phần** và **thay thế toàn bộ bản ghi**, xử lý đúng missing/null, triển khai cập nhật có điều kiện theo version trong Java, bảo vệ các ràng buộc khi nhiều tác vụ ghi đồng thời và lựa chọn chiến lược phù hợp với vòng đời, bảo mật và yêu cầu vận hành của dữ liệu.

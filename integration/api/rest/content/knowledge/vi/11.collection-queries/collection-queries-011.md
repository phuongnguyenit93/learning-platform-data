# Chọn trường trả về và mở rộng quan hệ có kiểm soát

## 1. Bài toán của truy vấn tập hợp trong REST API

Trong REST API, tài nguyên và tập hợp tài nguyên được định danh bằng URI; client sử dụng GET để truy vấn representation phù hợp với quyền của mình. Một endpoint như GET /api/orders có thể phục vụ nhiều giao diện: danh sách đơn gọn, bảng quản trị có tổng tiền, trang chi tiết cần thông tin khách hàng và dòng hàng. Nếu API luôn trả toàn bộ mọi trường và quan hệ, một yêu cầu xem danh sách có thể trở thành phép đọc hàng nghìn bản ghi kèm nhiều bảng phụ.

Hai khả năng thường được thêm vào hợp đồng truy vấn:

- **Sparse field selection (chọn trường trả về):** client yêu cầu một tập con các trường trong representation, chẳng hạn id, status và totalAmount.
- **Controlled relationship expansion (mở rộng quan hệ có kiểm soát):** client yêu cầu server nhúng một số tài nguyên liên quan được cho phép, chẳng hạn customer hoặc items.product, thay vì chỉ nhận ID/liên kết.

Ví dụ minh họa:

~~~http
GET /api/orders?fields=id,status,totalAmount&expand=customer&limit=2 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Một response có thể trông như sau:

~~~json
{
  "data": [
    {
      "id": "ord-101",
      "status": "CONFIRMED",
      "totalAmount": 350000,
      "customer": {
        "id": "cus-8",
        "displayName": "Khách hàng A"
      }
    },
    {
      "id": "ord-102",
      "status": "PENDING_PAYMENT",
      "totalAmount": 200000,
      "customer": {
        "id": "cus-9",
        "displayName": "Khách hàng B"
      }
    }
  ],
  "page": {
    "limit": 2,
    "nextCursor": "opaque-example-token"
  }
}
~~~

Ở đây, fields và expand **là quy ước do API trong bài định nghĩa**, không phải tham số bắt buộc của HTTP/REST. Những API khác có thể dùng select, include, fields[type], expand[] hoặc các cách mã hóa khác. Điều quan trọng là có **một hợp đồng ổn định, giới hạn rõ và được tài liệu hóa**.

**Mục tiêu bài học:** thiết kế tập trường và quan hệ được phép truy vấn, giới hạn chi phí mở rộng, bảo vệ dữ liệu nhiều tenant, tối ưu truy vấn SQL/ORM, phối hợp phân trang–cache–OpenAPI, và kiểm thử hợp đồng với Java/Spring hoặc công nghệ tương đương.

> **Nguyên tắc cốt lõi:** Client được chọn một phần **trong phạm vi dữ liệu mà server cho phép**. Tham số fields/expand là yêu cầu định hình kết quả, không phải cơ chế trao quyền đọc dữ liệu.

## 2. Tại sao không luôn trả toàn bộ dữ liệu?

### 2.1. Over-fetching và under-fetching

- **Over-fetching:** endpoint trả nhiều trường và quan hệ không cần thiết, tăng băng thông, thời gian serialize, CPU, bộ nhớ, thời gian query và rủi ro lộ thông tin.
- **Under-fetching:** endpoint trả quá ít dữ liệu, client phải gọi thêm nhiều request để hiển thị màn hình; có thể tạo thác request hoặc độ trễ mạng cao.

Ví dụ màn hình danh sách chỉ cần 20 đơn với id, status và totalAmount. Nếu server trả luôn notes nội bộ, địa chỉ chi tiết, tất cả dòng hàng, lịch sử thanh toán và log sự kiện, phần lớn payload không được dùng. Ngược lại, nếu chỉ trả orderId và mọi lần vẽ dòng đều cần gọi GET /orders/{id} rồi GET /customers/{id}, client có thể tạo hàng chục cuộc gọi.

**Chọn trường** giúp giảm trường không cần thiết; **mở rộng có kiểm soát** giúp giảm số vòng gọi phía client. Nhưng cả hai có thể làm server phức tạp hơn: truy vấn tùy biến, quyền theo trường, giới hạn mối quan hệ, cache có nhiều biến thể và chi phí join.

### 2.2. Một API linh hoạt không đồng nghĩa một truy vấn vô hạn

Cho phép expand mọi quan hệ tới độ sâu bất kỳ sẽ dẫn đến:

- Nhiều bảng được join hoặc load thành một đồ thị đối tượng rất lớn.
- Lỗi **N+1 query** khi ORM lazy-load từng quan hệ của từng phần tử.
- **Cartesian explosion** khi JOIN nhiều quan hệ one-to-many cùng lúc.
- Vòng lặp serializer như order → customer → orders → customer.
- Truy vấn vượt ngưỡng CPU/memory, rò rỉ thông tin hoặc vượt quyền giữa tenant.
- Khó cache vì vô số tổ hợp fields, expand, filter và sort.

Giới hạn không phải sự bất tiện tùy ý; chúng là phần của hợp đồng về **hiệu năng, độ tin cậy, bảo mật và chi phí**.

## 3. Phân biệt chọn trường, mở rộng quan hệ, lọc và phân trang

| Tính năng | Câu hỏi mà client đặt ra | Ví dụ | Tác động |
|---|---|---|---|
| **fields** | Mỗi bản ghi trả những trường nào? | fields=id,status,totalAmount | Điều chỉnh shape/payload |
| **expand** | Nhúng quan hệ được phép nào? | expand=customer | Thêm dữ liệu liên quan |
| **filter** | Bản ghi nào thuộc tập kết quả? | status=CONFIRMED | Thay đổi tập bản ghi |
| **sort** | Bản ghi được sắp xếp theo thứ tự nào? | sort=-createdAt,id | Thứ tự và keyset |
| **limit/cursor** | Trả bao nhiêu phần tử và trang nào? | limit=20&cursor=... | Kích thước trang, điều hướng |

Không lẫn **fields** với câu điều kiện SQL WHERE: fields không tự lọc các bản ghi. Không lẫn **expand** với filter bằng quan hệ: expand=customer chỉ yêu cầu representation customer, không có nghĩa chỉ trả các order có customer.

Ví dụ:

~~~http
GET /api/orders?status=CONFIRMED&fields=id,status,totalAmount&expand=customer&limit=20 HTTP/1.1
~~~

Thứ tự xử lý logic:

1. Xác thực caller và xác định tenant/phạm vi quyền.
2. Phân tích, validate các tham số filter/sort/fields/expand/limit.
3. Truy vấn **tập đơn được phép thấy**, sắp xếp ổn định và phân trang.
4. Tải dữ liệu quan hệ cho **những đơn thuộc trang hiện tại**, trong giới hạn hợp đồng và quyền.
5. Định hình mỗi representation, tạo liên kết/cursor, áp dụng chính sách cache.

Một triển khai có thể tối ưu các bước khác thứ tự mô tả, nhưng phải giữ **ngữ nghĩa quan sát được**. Đặc biệt, không lọc bản ghi chỉ dựa trên việc khách hàng có được quyền expand một quan hệ hay không, trừ khi filter nghiệp vụ quy định như vậy.

## 4. Chốt hợp đồng fields và expand trước khi viết code

Để có ví dụ nhất quán, bài này chọn **quy ước của OmniOrder API** như sau:

| Tham số | Quy ước | Khi vắng mặt |
|---|---|---|
| fields | Danh sách tên trường gốc, phân tách bằng dấu phẩy | Trả tập trường mặc định |
| expand | Danh sách đường dẫn quan hệ cho phép, phân tách bằng dấu phẩy | Không nhúng quan hệ tùy chọn |
| limit | Số đơn tối đa trong một trang; từ 1 đến 50 | 20 |
| cursor | Token trang opaque do server tạo | Trang đầu |
| status | Bộ lọc trạng thái nghiệp vụ hợp lệ | Không lọc theo status |
| sort | Thứ tự đã định nghĩa, ví dụ -createdAt,id | -createdAt,-id |

Trong ví dụ, **id luôn được trả về** để client định danh tài nguyên; nếu client bỏ id khỏi fields thì server tự bổ sung. fields chỉ lựa chọn **các trường scalar cấp order**. Trường quan hệ customer, items không được đưa vào fields; chúng được chọn qua expand. Các object được expand có **tập trường công khai mặc định riêng**; API ví dụ **chưa hỗ trợ chọn trường tùy ý của object lồng nhau**.

Hợp đồng nên ghi rõ:

- **Trường mặc định của order:** id, status, totalAmount, createdAt.
- **Trường có thể chọn:** id, status, totalAmount, createdAt. Không công khai internalNotes, paymentToken, tenantId qua fields.
- **Quan hệ có thể expand:** customer, items, items.product.
- **Đường dẫn con:** expand=items.product tự yêu cầu tải items trước; không cần khai báo items đồng thời.
- **Giới hạn:** độ sâu quan hệ tối đa 2, limit tối đa 50, cùng một request không vượt **ngân sách chi phí mở rộng** do server quy định.
- **Chuẩn hóa:** dấu cách quanh tên bị loại bỏ, các tên trùng được gộp, tên phải phân biệt đúng chữ hoa/thường.
- **Không hợp lệ:** fields= trống, tên không được hỗ trợ, expand không được cho phép, vượt depth/cost, limit ngoài phạm vi → **400 Bad Request** với Problem Details phù hợp.
- **Không có quyền xem dữ liệu:** xử lý theo chính sách phân quyền trước khi trả representation; request fields/expand không được bỏ qua kiểm tra quyền.

Lựa chọn **tự bổ sung id** và **trả 400 khi tên không được hỗ trợ** là chính sách của ví dụ này. Một API khác có thể yêu cầu id phải được liệt kê hoặc bỏ qua tên không hỗ trợ; tuy nhiên phải công bố, kiểm thử và dùng nhất quán. Với API công khai, trả lỗi rõ ràng thường an toàn hơn việc âm thầm bỏ qua một yêu cầu làm client tưởng đã nhận dữ liệu.

### 4.1. Ví dụ chọn trường

~~~http
GET /api/orders?fields=status,totalAmount HTTP/1.1
Authorization: Bearer <access-token>
~~~

~~~json
{
  "data": [
    {"id": "ord-101", "status": "CONFIRMED", "totalAmount": 350000},
    {"id": "ord-102", "status": "PENDING_PAYMENT", "totalAmount": 200000}
  ],
  "page": {"limit": 20, "nextCursor": null}
}
~~~

Server bổ sung id, nhưng **không trả createdAt** vì client không yêu cầu và fields đã được chỉ định rõ. Khi client không gửi fields, order sẽ dùng bộ trường mặc định.

### 4.2. Ví dụ mở rộng một quan hệ

~~~http
GET /api/orders?fields=id,status&expand=customer&limit=1 HTTP/1.1
Authorization: Bearer <access-token>
~~~

~~~json
{
  "data": [
    {
      "id": "ord-101",
      "status": "CONFIRMED",
      "customer": {
        "id": "cus-8",
        "displayName": "Khách hàng A"
      }
    }
  ],
  "page": {"limit": 1, "nextCursor": null}
}
~~~

Quan hệ xuất hiện vì expand, **không phụ thuộc vào việc customer có nằm trong fields hay không**. Nested customer có thể sở hữu dữ liệu riêng; chỉ các trường được phép của customer mới được trả. Đây là quy tắc hợp đồng cần nêu rõ, tránh mỗi endpoint diễn giải khác nhau.

### 4.3. Ví dụ mở rộng quan hệ hai cấp

~~~http
GET /api/orders?fields=id,status&expand=items.product&limit=1 HTTP/1.1
Authorization: Bearer <access-token>
~~~

~~~json
{
  "data": [
    {
      "id": "ord-101",
      "status": "CONFIRMED",
      "items": [
        {
          "id": "line-1",
          "quantity": 2,
          "product": {
            "id": "prod-1",
            "name": "Sổ tay"
          }
        },
        {
          "id": "line-2",
          "quantity": 1,
          "product": {
            "id": "prod-2",
            "name": "Bút mực"
          }
        }
      ]
    }
  ],
  "page": {"limit": 1, "nextCursor": null}
}
~~~

Nếu một sản phẩm đã ngừng bán, API cần quy định liệu product được nhúng bằng snapshot trong order, bản ghi hiện tại hay null/link lịch sử. **Đây là quyết định nghiệp vụ**: không để expand làm đổi tổng tiền, trạng thái đơn hoặc ngữ nghĩa của dữ liệu đã chốt.

### 4.4. Ví dụ bị từ chối

~~~http
GET /api/orders?fields=id,paymentToken&expand=payments.card HTTP/1.1
Authorization: Bearer <access-token>
~~~

Nếu paymentToken và payments.card nằm ngoài hợp đồng cho phép, request bị từ chối:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/invalid-query-shape",
  "title": "Invalid query shape",
  "status": 400,
  "detail": "Yêu cầu chọn trường hoặc mở rộng không được hỗ trợ",
  "code": "INVALID_QUERY_SHAPE"
}
~~~

**Không trả danh sách bí mật các trường nội bộ** qua thông báo lỗi. Với dữ liệu có quyền đọc riêng, có thể trả 403 cho yêu cầu chọn trường đã được công bố nhưng caller thiếu quyền, hoặc trả lỗi chung theo chính sách che giấu. Không thể thay thế kiểm tra authorization bằng việc chỉ lọc danh sách fields.

## 5. Mở rộng quan hệ: kiểm soát độ sâu, breadth và chi phí

### 5.1. Giới hạn depth không đủ

Một phép expand=items chỉ có độ sâu 1 nhưng một order có thể chứa 5.000 dòng hàng. Ngược lại, expand=customer sâu 1 nhưng chỉ thêm một object. Vì vậy không chỉ giới hạn số dấu chấm trong đường dẫn; cần xét:

- **Depth:** số bước qua quan hệ, chẳng hạn items.product sâu 2.
- **Fan-out/breadth:** số phần tử có thể được nhúng tại mỗi quan hệ.
- **Payload bytes:** kích thước serialization và truyền mạng.
- **Query cost:** số truy vấn, JOIN, hàng đọc, I/O và mức phân tán.
- **Resource permissions:** quyền đọc mỗi quan hệ, kể cả dữ liệu liên tenant.
- **Latency budget:** tổng thời gian từ client tới response và SLO endpoint.

Khi một object có nhiều quan hệ one-to-many, mở đồng thời nhiều collection không có giới hạn có thể nhân số bản ghi trung gian, dù độ sâu vẫn nhỏ.

### 5.2. Allowlist quan hệ và ngân sách chi phí ví dụ

Giả sử API quy định điểm chi phí để **chặn những tổ hợp phổ biến quá nặng**:

| Đường dẫn expand | Depth | Điểm chi phí minh họa | Giới hạn/phản hồi |
|---|---:|---:|---|
| customer | 1 | 1 | Một khách hàng hiện hành được phép thấy |
| items | 1 | 2 | Tối đa 100 dòng hàng mỗi đơn |
| items.product | 2 | 4 | Bao gồm items và product công khai của mỗi dòng |
| payments | 1 | Không hỗ trợ | Phản hồi 400 vì quan hệ bị loại khỏi public contract |
| items.product.supplier | 3 | Không hỗ trợ | Phản hồi 400 vì depth vượt giới hạn |

**Ngân sách tối đa của ví dụ là 5 điểm.** Request expand=customer,items.product có giá trị 1+4=5 và được phép nếu không vượt giới hạn runtime khác. Request expand=items,items.product **không bị cộng cả 2 và 4**, vì items là quan hệ cha đã bao hàm trong items.product; chuẩn hóa thành cấu trúc expansion duy nhất, có giá 4.

Đây là mô hình heuristic của bài học, **không phải thước đo chi phí DB phổ quát**. Chi phí thực tế có thể phụ thuộc số dòng, selectivity, tenant, index, dataset và cache hit. Chạy benchmark và theo dõi p95/p99 để hiệu chỉnh các điểm.

### 5.3. Giới hạn quan hệ collection

Với orders một trang có 50 order và mỗi order có 100 items, expand=items có thể tạo tới 5.000 item trong một response. Nếu từng item được mở rộng product, payload có thể còn lớn hơn. Một API có thể lựa chọn:

1. Cho phép expand=items nhưng ràng buộc cứng **tối đa N items trên mỗi order**, có trạng thái truncation và URI lấy tiếp.
2. Chỉ cho expand quan hệ một-một hoặc nhiều-một (customer), còn collection lớn buộc đọc endpoint con riêng, ví dụ GET /api/orders/{id}/items.
3. Hỗ trợ **pagination riêng cho nested collection** với hợp đồng rõ, nếu nghiệp vụ thực sự cần.

Không được **âm thầm cắt bớt items** rồi khiến client tưởng đó là toàn bộ đơn. Nếu một quan hệ bị giới hạn, response phải cho biết hasMore, next link hoặc từ chối expansion theo hợp đồng. Trong bài này, giả định đơn hàng có tối đa 100 dòng theo luật nghiệp vụ nên toàn bộ items có thể nhúng; nếu luật thay đổi, giới hạn phải được đánh giá lại.

### 5.4. Tránh vòng tham chiếu

Đồ thị có thể gồm:

~~~mermaid
flowchart LR
    O[Order] --> C[Customer]
    C --> OL[Orders của customer]
    OL --> C
    O --> I[Order items]
    I --> P[Product]
    P --> OTHER[Supplier / Category / ...]
~~~

Không cho client yêu cầu chuỗi customer.orders.customer.orders vô hạn. Allowlist, depth cap và schema DTO giúp tránh serializer duyệt đồ thị ORM trực tiếp. Thư viện JSON có annotation chống vòng tham chiếu chỉ là một lớp kỹ thuật, **không thay cho hợp đồng mở rộng an toàn**.

### 5.5. Vì sao không đơn giản "expand=*"?

Wildcard làm phạm vi dữ liệu phụ thuộc vào các quan hệ mới được thêm ở backend. Sau một lần nâng cấp schema, cùng request có thể bất ngờ trả thêm thông tin nhạy cảm hoặc tăng tải. Nếu có wildcard, nó phải là tập cố định được version rõ ràng; với API công khai, **allowlist tường minh** thường dễ kiểm soát và dự báo hơn.

## 6. Phân quyền là giới hạn cứng của cả fields lẫn expand

### 6.1. Quyền theo resource, field và relationship

Khi nhận GET /api/orders?fields=id,totalAmount&expand=customer, server phải bảo vệ ba lớp:

1. **Resource-level:** caller có quyền xem các order nào theo user, role, tenant và trạng thái nghiệp vụ?
2. **Field-level:** caller có được xem totalAmount hoặc các trường khác của order không?
3. **Relationship-level:** caller có quyền xem customer tương ứng, và trong đó được thấy những trường nào?

Một token có scope orders.read **không tự động** cấp quyền customer.pii.read. Ngay cả khi customer cùng tenant, có thể phải ẩn email, số điện thoại và địa chỉ. Trong ví dụ, expanded customer chỉ trả id và displayName. Đừng nhúng trực tiếp entity Customer chứa mật khẩu băm, internal risk score hoặc thông tin định danh nhạy cảm.

### 6.2. Quyền trước projection và serialization

Một pipeline an toàn có thể được mô tả như sau:

~~~mermaid
flowchart TD
    R[GET /api/orders có fields và expand] --> A[Authentication: token / session hợp lệ]
    A --> B[Authorization: scope, tenant, ACL]
    B --> C[Parse và validate query shape]
    C --> D[Query tập orders trong phạm vi được phép]
    D --> E[Load relationships theo allowlist và quyền]
    E --> F[Projection / DTO chỉ gồm trường được phép]
    F --> G[Serialize, cache policy, response]
    C --> X[400 hoặc 403 có kiểm soát nếu query bị cấm]
    B --> Y[401 / 403 / 404 theo chính sách]
~~~

Thứ tự cụ thể giữa parse và một số kiểm tra quyền có thể khác nhau tùy framework, nhưng **không được truy vấn và tiết lộ dữ liệu chưa được ủy quyền**. Hợp đồng cần nhất quán khi request có cả query sai lẫn credential không hợp lệ để tránh lộ thông tin qua thông báo lỗi.

### 6.3. Data ownership và nhiều tenant

Một anti-pattern:

~~~sql
-- Không an toàn nếu truy vấn trước không giới hạn tenant
SELECT * FROM orders WHERE id IN (:ids);
~~~

Một hướng an toàn hơn cho dữ liệu nhiều tenant:

~~~sql
SELECT o.id, o.status, o.total_amount
FROM orders o
WHERE o.tenant_id = :authenticatedTenantId
  AND o.id IN (:ids);
~~~

Với customer và items liên quan, áp dụng điều kiện quyền tương đương. Truy vấn chỉ dựa vào customerId truyền từ URL/body sẽ không thay thế kiểm tra tenant hoặc ACL. Nếu có tài nguyên liên tenant hợp pháp, cần một mô hình ủy quyền rõ và audit đúng thay vì bỏ bộ lọc tenant chung.

**Ví dụ nguy hiểm:** trang danh sách tenant A cho phép expand=customer. Nếu backend join orders với customers chỉ theo customer_id, lỗi dữ liệu hoặc ID bị cấu hình sai có thể kéo theo customer của tenant B. Khi đó cả route danh sách lẫn serializer có thể lộ thông tin. Kiểm thử phải bao gồm quan hệ bị hỏng hoặc bị gán sai tenant, không chỉ dữ liệu bình thường.

### 6.4. Client yêu cầu trường không có quyền

Có hai chính sách phổ biến:

- **Từ chối rõ (strict):** field đã được công bố nhưng caller không có quyền thì trả 403 Forbidden, nếu việc công khai tên field không gây rủi ro.
- **Che giấu:** trả lỗi chung không phân biệt "field không tồn tại" với "field bị cấm" (hoặc hoàn toàn không quảng bá field nhạy cảm), để tránh enumeration.

Không âm thầm trả trường nhạy cảm chỉ vì client biết tên field. Cũng không sử dụng **fields** như cách xóa các trường bí mật sau khi đã serialize một entity đầy đủ rồi ghi ra log/cache trước đó. Quyền và projection phải được áp dụng **trước khi phát response**, cả trên đường thành công, lỗi và debug.

## 7. Tránh N+1 query khi expand collection

### 7.1. Hiểu đúng N+1

Giả sử API trả 20 order. Backend chạy một query lấy danh sách 20 order, sau đó trong vòng lặp đọc order.getCustomer() với quan hệ lazy chưa tải:

~~~text
1 query:   SELECT orders LIMIT 20
20 query:  SELECT customers WHERE id = ? (mỗi order một lần)
---------------------------------------------------------
21 query cho một request, chưa kể items và product
~~~

Nếu mỗi order lại có 10 items và mỗi item cần tải product, số query có thể tăng đáng kể. N+1 làm latency và tải DB tăng cùng kích thước trang ngay cả khi response chỉ hiển thị vài trường.

**N+1 không phải lỗi của JSON hay của riêng JPA**. Nó là cách fetch dữ liệu không được batch phù hợp với đơn vị xử lý của request.

### 7.2. Các cách tải dữ liệu

| Chiến lược | Phù hợp | Điểm cần chú ý |
|---|---|---|
| **SQL projection** chỉ chọn cột cần thiết | Danh sách chỉ đọc, fieldset ít biến thể | Cần map DTO, query có thể cần nhiều hình dạng |
| **JOIN FETCH / EntityGraph** cho quan hệ single-valued | Một vài quan hệ many-to-one/one-to-one | JOIN nhiều collection dễ nở hàng; pagination có thể sai |
| **Batch loading** theo danh sách ID | customer, items, product trên một trang orders | Giới hạn IN list và quyền, group dữ liệu theo parent |
| **Read model / materialized view** | Danh sách cần thống kê/phép tổng hợp phức tạp | Phải nói rõ độ trễ đồng bộ và freshness |
| **Cache** theo khóa và scope phù hợp | Dữ liệu ít thay đổi, được truy cập nhiều | Cache invalidation, phân quyền, negative caching |
| **Endpoint con riêng** | Quan hệ collection có kích thước lớn | Client gọi thêm nhưng kiểm soát pagination tốt hơn |

Chọn chiến lược bằng trace/benchmark ở dữ liệu thực, không mặc định eager loading toàn bộ quan hệ là tối ưu.

### 7.3. Hai giai đoạn: phân trang root rồi mới load quan hệ

Đối với endpoint danh sách có expand=items.product:

1. Query order ID và cột cần thiết **với filter/sort/limit/cursor**.
2. Với tập order IDs của trang, query **tất cả items** bằng một hoặc một số batch.
3. Với tập product IDs liên quan, query **tất cả product được phép nhúng** theo batch.
4. Group items theo orderId và gắn product theo productId trong DTO.
5. Serialize đúng fieldset và quan hệ cho phép.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Orders API
    participant D as Database
    C->>A: GET /orders?limit=20&expand=items.product
    A->>D: Query trang 20 orders theo tenant/sort/cursor
    D-->>A: 20 orders + IDs
    A->>D: Query items WHERE order_id IN (page IDs)
    D-->>A: Items của trang
    A->>D: Query products WHERE id IN (item product IDs)
    D-->>A: Product được phép
    A->>A: Ghép DTO theo parent ID, áp dụng quyền
    A-->>C: 200 + page + relationships
~~~

Số query có thể xấp xỉ cố định đối với trang nhỏ, dù số order trong trang tăng. Tuy nhiên, số hàng dữ liệu và kích thước response vẫn tăng. Batch loading không miễn trừ **payload cap, quyền, timeout và giới hạn fan-out**.

### 7.4. Vì sao JOIN nhiều one-to-many có thể phá phân trang?

Ví dụ:

~~~sql
-- Minh họa vấn đề: LIMIT áp dụng cho hàng JOIN, không phải 20 order phân biệt
SELECT o.id, i.id, p.id
FROM orders o
LEFT JOIN order_items i ON i.order_id = o.id
LEFT JOIN products p ON p.id = i.product_id
WHERE o.tenant_id = :tenantId
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20;
~~~

Nếu một order có 15 items, 20 hàng JOIN có thể chỉ chứa một hoặc hai order. Phân trang kết quả sau JOIN **không tương đương** phân trang 20 order gốc. Có thể phát sinh thiếu order, trùng bản ghi hoặc mất dữ liệu trong nested collection.

Đối với Spring Data JPA, khi fetch một collection bằng join mà đồng thời dùng pagination, một số cấu hình/provider có thể cảnh báo, phân trang trong bộ nhớ hoặc gây lỗi; cần hiểu behavior từng phiên bản. Một chiến lược phổ biến là **query trang root trước, fetch quan hệ theo IDs sau**.

### 7.5. Query projection và trường nội bộ phục vụ xử lý

Giả sử client chỉ yêu cầu fields=status,totalAmount. Backend vẫn có thể cần id để định danh, createdAt để tạo cursor, tenantId để kiểm tra quyền và version để tính ETag. **Các cột phục vụ nội bộ không nhất thiết được trả ra response**.

Tránh hai cực đoan:

- Chỉ SELECT đúng những cột client gửi, làm mất khóa phục vụ authorization/sort/cursor.
- SELECT tất cả cột/quan hệ rồi chỉ xóa field khi serialize, tạo chi phí và rủi ro dữ liệu dư không cần thiết.

Thiết kế query model/DTO để tách **dữ liệu cần tải và dữ liệu được phép công khai**.

## 8. Phối hợp fields và expand với phân trang

### 8.1. Phân trang root collection

Với GET /api/orders?limit=20, server phân trang **orders**, không phân trang các row tạo ra bởi JOIN. Một response nên có metadata rõ:

~~~json
{
  "data": [
    {"id": "ord-101", "status": "CONFIRMED"},
    {"id": "ord-102", "status": "PENDING"}
  ],
  "page": {
    "limit": 2,
    "nextCursor": "opaque-next-page-token"
  }
}
~~~

**Số phần tử trong một trang** là số orders, không phải số order items được nhúng. Nếu có nested collection, hạn mức nested là một ràng buộc riêng và cần tài liệu hóa.

### 8.2. Keyset/cursor pagination và thứ tự ổn định

Offset pagination có thể tốn chi phí khi offset lớn và dịch chuyển kết quả khi có dữ liệu mới. Với tập lớn, cursor/keyset dựa trên thứ tự ổn định thường phù hợp.

Ví dụ thứ tự mặc định là createdAt DESC, id DESC; để lấy trang tiếp theo sau cặp giá trị (lastCreatedAt, lastId), một query PostgreSQL minh họa:

~~~sql
SELECT
    o.id, o.status, o.total_amount, o.created_at
FROM orders o
WHERE o.tenant_id = :authenticatedTenantId
  AND (
       o.created_at < :lastCreatedAt
       OR (o.created_at = :lastCreatedAt AND o.id < :lastId)
  )
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limitPlusOne;
~~~

Trong trang đầu chưa có cursor thì bỏ điều kiện keyset. Lấy **limit + 1** bản ghi để xác định có trang tiếp theo. Kiểu dữ liệu id và phép so sánh cần phù hợp DB/schema; query là minh họa, không phải SQL cho mọi hệ quản trị.

**Cursor opaque không phải authorization token.** Nó có thể chứa hoặc tham chiếu đến sort key và filter context, nhưng cần được mã hóa/ký hoặc xác thực chống sửa tùy thiết kế, ràng buộc với tenant/scope/filter/sort khi phù hợp, có chính sách hết hạn và không lộ PII. Client không nên tự xây cursor bằng cách sửa JSON Base64.

### 8.3. Khi chuyển trang, giữ query shape

Nếu client đang xem:

~~~http
GET /api/orders?status=CONFIRMED&fields=id,status&expand=customer&limit=20
~~~

thì trang tiếp theo vẫn phải áp dụng **status, fields, expand, limit, sort và quyền** tương ứng. Có hai cách:

1. Client tự giữ tham số cũ và chỉ thay cursor.
2. Server trả next link đã encode đầy đủ và chính xác query context.

Nếu cursor được gắn với query shape, thay expand/fields/filter giữa các trang có thể cần **khởi động lại pagination**, thay vì chấp nhận token không tương thích. Cần nói rõ trong hợp đồng.

### 8.4. Nhất quán qua nhiều trang

Cursor giảm một số vấn đề của offset nhưng **không tự tạo snapshot transaction xuyên nhiều request**. Trong lúc client lấy các trang, order có thể được tạo, xóa hoặc đổi trạng thái, và các bản ghi có thể dịch chuyển tùy sort/filter. Nếu nghiệp vụ yêu cầu ảnh chụp nhất quán, cần cơ chế snapshot token, thời điểm chốt hoặc read model tương ứng, với chi phí và giới hạn được công bố.

## 9. Cache, ETag và tính đúng của representation

### 9.1. Mỗi query shape có thể là một representation khác

Hai URI:

~~~http
GET /api/orders?fields=id,status&limit=20
GET /api/orders?fields=id,status,totalAmount&expand=customer&limit=20
~~~

trả hai shape khác nhau. Một cache key không phân biệt query string có thể trả sai dữ liệu. Cần đảm bảo cache ở gateway/CDN/application **phân biệt query parameters có ảnh hưởng representation**.

Ngoài URI, kết quả có thể phụ thuộc vào Authorization, tenant, locale, feature flag hoặc các chính sách dữ liệu. Với tài nguyên cá nhân như orders, ví dụ thường dùng:

~~~http
Cache-Control: private, no-store
~~~

Ở đây no-store yêu cầu cache không lưu response, còn private giới hạn shared cache; khi đã có no-store, private có thể dư nhưng cho biết rõ ý định. Không có header chung bắt buộc cho mọi endpoint: dữ liệu công khai có thể cache theo TTL có chủ đích.

### 9.2. Chuẩn hóa tham số để tránh cache fragmentation

Hai request:

~~~text
fields=id,status&expand=customer
expand=customer&fields=status,id
~~~

có thể có cùng ngữ nghĩa theo hợp đồng của bài. Nếu cache key dùng toàn bộ raw query string, chúng tạo hai biến thể khác nhau. Có thể chuẩn hóa/sắp xếp tập fields và expand trong pipeline cache để giảm fragmentation, **nhưng phải đảm bảo normalization tương thích hành vi API**, không tự ý loại tham số có ý nghĩa hoặc gộp các URI không tương đương.

### 9.3. ETag phải đại diện cho đúng shape và quyền

Nếu API trả ETag cho một representation, validator cần được tính theo bản thể hiện được trả (hoặc cơ chế phiên bản bảo đảm sự tương ứng), không đơn thuần dùng một version field bỏ qua những quan hệ được expand đã thay đổi.

Ví dụ order không thay đổi nhưng customer.displayName vừa đổi. Khi request expand=customer, representation có thể thay đổi dù order.version giữ nguyên. Nếu ETag chỉ dựa trên order.version, server có thể trả **304 Not Modified sai** và client tiếp tục hiển thị dữ liệu cũ.

Điều kiện để trả 304:

1. Người gọi vẫn có quyền đọc representation tương ứng.
2. Request và variant (fields/expand, locale, những yếu tố liên quan) được xác định đúng.
3. Validator khớp theo ngữ nghĩa của representation hiện tại.
4. Quy tắc điều kiện HTTP được đánh giá theo thứ tự thích hợp.

Đừng dùng ETag như đường tắt bỏ qua authorization hoặc để cache của một tenant phục vụ tenant khác.

### 9.4. Cache response có PII

Với expand=customer, response có thể chứa dữ liệu cá nhân. Trước khi bật cache tại CDN, cần đánh giá phân quyền, nội dung và cache keys; nhiều trường hợp nên để **no-store** trên API orders. Nếu dùng cache riêng per-user/tenant, cần kiểm soát key, thời gian tồn tại, invalidation và chính sách xóa dữ liệu.

## 10. Xây dựng bộ phân tích query shape bằng Java

Một implementation an toàn không lấy trực tiếp tên field từ client để nối thành SELECT, JOIN hoặc biểu thức reflection. Trước tiên nó chuyển query string thành **một kế hoạch đã được validate** theo allowlist.

### 10.1. Kiểu dữ liệu cho yêu cầu chọn trường

Ví dụ sau phù hợp Java hiện đại (record, Stream.toList). Có thể tách code thành các source file tương ứng của dự án.

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

record OrderReadShape(
        Set<String> fields,
        Set<String> expands,
        int limit,
        String cursor) {

    private static final Set<String> ALLOWED_FIELDS = Set.of(
            "id", "status", "totalAmount", "createdAt");

    private static final Set<String> ALLOWED_EXPANSIONS = Set.of(
            "customer", "items", "items.product");

    private static final Set<String> DEFAULT_FIELDS = Set.of(
            "id", "status", "totalAmount", "createdAt");

    static OrderReadShape parse(
            String rawFields,
            String rawExpand,
            int limit,
            String cursor) {

        if (limit < 1 || limit > 50) {
            throw new InvalidQueryShapeException(
                    "limit must be between 1 and 50");
        }

        Set<String> fields = rawFields == null
                ? new LinkedHashSet<>(DEFAULT_FIELDS)
                : parseCsv(rawFields, ALLOWED_FIELDS);

        // id luôn có mặt để định danh resource theo hợp đồng này.
        fields.add("id");

        Set<String> expansions = rawExpand == null
                ? new LinkedHashSet<>()
                : parseCsv(rawExpand, ALLOWED_EXPANSIONS);

        // Quan hệ sâu ngầm yêu cầu quan hệ cha.
        if (expansions.contains("items.product")) {
            expansions.add("items");
        }

        int cost = 0;
        if (expansions.contains("customer")) {
            cost += 1;
        }
        if (expansions.contains("items.product")) {
            cost += 4;
        } else if (expansions.contains("items")) {
            cost += 2;
        }

        if (cost > 5) {
            throw new InvalidQueryShapeException(
                    "Expansion budget exceeded");
        }

        return new OrderReadShape(
                Collections.unmodifiableSet(fields),
                Collections.unmodifiableSet(expansions),
                limit,
                cursor);
    }

    private static Set<String> parseCsv(
            String raw,
            Set<String> allowed) {

        if (raw.isBlank()) {
            throw new InvalidQueryShapeException(
                    "Empty query selection");
        }

        List<String> names = Arrays.stream(
                    raw.split(",", -1))
                .map(String::trim)
                .toList();

        LinkedHashSet<String> result = new LinkedHashSet<>();
        for (String name : names) {
            if (name.isBlank() || !allowed.contains(name)) {
                throw new InvalidQueryShapeException(
                        "Unsupported query selection");
            }
            result.add(name);
        }
        return result;
    }
}

final class InvalidQueryShapeException extends RuntimeException {
    InvalidQueryShapeException(String message) {
        super(message);
    }
}
~~~

Các chi tiết đáng chú ý:

- **Allowlist:** chỉ các trường và quan hệ công bố được chấp nhận, không cho truyền tên cột/table tùy ý.
- **Danh sách rỗng/tên trống:** fields= hoặc fields=id,,status bị từ chối; không âm thầm loại bỏ thành phần sai.
- **Trùng tên:** fields=id,id,status được gộp nhưng vẫn hợp lệ; không tăng chi phí.
- **Đường dẫn sâu:** items.product tự thêm items, không tính điểm cho parent hai lần.
- **Limit:** từ 1 đến 50 theo hợp đồng minh họa.
- **Cursor:** chưa được giải mã trong parser; tầng pagination cần xác thực nội dung, scope và thời hạn riêng.

Ví dụ không giải quyết mọi ràng buộc như tổng số tham số, độ dài URL, trường có quyền theo role hoặc quan hệ trên từng resource. Những chính sách đó cần được bổ sung ở gateway/application và **không thay thế authorization**.

### 10.2. Dùng parser trong Spring MVC

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrdersQueryController {
    private final AuthorizedOrdersQuery query;

    OrdersQueryController(AuthorizedOrdersQuery query) {
        this.query = query;
    }

    @GetMapping("/api/orders")
    ResponseEntity<OrderPageView> listOrders(
            @RequestParam(required = false) String fields,
            @RequestParam(required = false) String expand,
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(required = false) String cursor,
            @AuthenticationPrincipal Jwt jwt) {

        OrderReadShape shape =
                OrderReadShape.parse(fields, expand, limit, cursor);

        // CallerScope phải được tạo từ JWT đã xác thực và
        // policy của server; không tin tenantId từ query string.
        CallerScope caller = CallerScope.fromVerifiedJwt(jwt);
        OrderPageView result = query.listVisible(caller, shape);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(result);
    }
}
~~~

AuthorizedOrdersQuery, CallerScope và OrderPageView là các interface/kiểu minh họa của ứng dụng. Phần khó nhất nằm ở **listVisible**: truy vấn trong phạm vi tenant/ACL, phân trang root, batch-load quan hệ, kiểm tra field/relationship policy và tạo DTO công khai.

Nếu client truyền limit=abc, Spring có thể phát sinh lỗi conversion trước khi parser được gọi. Cần handler cho **MethodArgumentTypeMismatchException** hoặc loại ngoại lệ tương ứng để trả 400 có hợp đồng, thay vì chỉ bắt InvalidQueryShapeException.

### 10.3. Trả Problem Details cho query shape không hợp lệ

~~~java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class QueryErrorAdvice {

    @ExceptionHandler(InvalidQueryShapeException.class)
    ResponseEntity<ProblemDetail> invalidShape(
            InvalidQueryShapeException exception) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        problem.setType(URI.create(
                "https://api.example.test/problems/invalid-query-shape"));
        problem.setTitle("Invalid query shape");
        problem.setDetail(
                "Các tham số chọn trường hoặc mở rộng không hợp lệ");
        problem.setProperty("code", "INVALID_QUERY_SHAPE");

        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .contentType(MediaType.valueOf(
                        "application/problem+json"))
                .body(problem);
    }
}
~~~

Exception nội bộ có thể ghi chi tiết để điều tra nhưng không mặc định copy exception.getMessage() ra response. Ví dụ parser cố ý dùng thông báo công khai chung, tránh để người gọi thăm dò tên quan hệ hoặc trường nhạy cảm không được công bố.

### 10.4. Không trả JPA entity thẳng ra JSON

Kiểu dữ liệu ORM thường chứa quan hệ hai chiều, proxy lazy-load và trường nội bộ; serializer có thể kích hoạt query mới hoặc xuất dữ liệu không mong muốn. Nên tạo **public response DTO** với bộ trường đã xác định và một assembler tường minh.

Ví dụ cấu trúc response logic:

~~~java
record CustomerPreview(String id, String displayName) {}
record ProductPreview(String id, String name) {}
record OrderItemPreview(
        String id,
        int quantity,
        ProductPreview product) {}

record PageInfo(int limit, String nextCursor) {}
record OrderPageView(
        java.util.List<java.util.Map<String, Object>> data,
        PageInfo page) {}
~~~

Map<String,Object> ở đây chỉ minh họa tập trường động. Khi có ít biến thể, **DTO typed rõ ràng hoặc các projection classes chuyên biệt** thường dễ kiểm soát schema và hiệu năng hơn. Nếu dùng map, chỉ đưa vào giá trị do assembler chọn từ allowlist, không đưa raw entity hoặc raw column map.

Một assembler có thể làm:

~~~java
// Pseudocode: cột đã tải và quan hệ đã được kiểm tra quyền
for (OrderRow order : pageRows) {
    Map<String, Object> output = new LinkedHashMap<>();
    output.put("id", order.id());

    if (shape.fields().contains("status")) {
        output.put("status", order.status());
    }
    if (shape.fields().contains("totalAmount")) {
        output.put("totalAmount", order.totalAmount());
    }
    if (shape.fields().contains("createdAt")) {
        output.put("createdAt", order.createdAt());
    }
    if (shape.expands().contains("customer")) {
        output.put("customer", authorizedCustomerPreview(order));
    }
    if (shape.expands().contains("items")) {
        output.put("items", authorizedItemPreviews(order, shape));
    }
    results.add(output);
}
~~~

Đây là **pseudocode Java**: các kiểu, biến và hàm chưa được khai báo trong fragment. Trong triển khai thật, các hàm preview phải dùng dữ liệu đã batch-load và được phân quyền, không tự query từng order làm phát sinh N+1.

## 11. Thêm quan hệ phải giữ ngữ nghĩa tài nguyên

### 11.1. Đối tượng tham chiếu hay bản chụp tại thời điểm giao dịch?

Trong thương mại điện tử, một order đã chốt cần lưu tên, đơn giá và quy tắc tại thời điểm mua theo nghiệp vụ. Nếu expand=items.product đọc bảng Product hiện tại, giá/nội dung catalog có thể đã thay đổi. Do đó:

- Các thuộc tính **snapshot trong order item** (ví dụ unitPriceAtPurchase) nên được sở hữu bởi Ordering.
- Quan hệ **product hiện hành** có thể dùng cho thông tin danh mục cập nhật.
- API phải đặt tên trường và mô tả hợp đồng để client không nhầm currentPrice với giá đã mua.

Không để một phép mở rộng quan hệ làm biến đổi tính bất biến của dữ liệu lịch sử.

### 11.2. Quan hệ optional, đã xóa hoặc không thể truy cập

Giả sử customer từng tồn tại nhưng được xóa hoặc ẩn. Khi expand=customer, có nhiều cách biểu diễn:

- customer: null, nếu schema công bố rõ quan hệ có thể vắng mặt.
- Không nhúng customer và chỉ giữ customerId/link nếu client được phép thấy ID.
- Từ chối yêu cầu expand cụ thể với lỗi phân quyền phù hợp.
- Trả một snapshot công khai tối thiểu nếu nghiệp vụ được phép lưu và chia sẻ.

Mỗi lựa chọn có hậu quả về schema và UX. **Không tự thay quan hệ bị cấm bằng dữ liệu placeholder có thể tiết lộ trạng thái**. Đặc biệt, 404 của một resource phụ không có nghĩa GET collection chính phải thất bại toàn bộ, trừ khi hợp đồng yêu cầu tính nguyên tử của expansion.

### 11.3. Link-only là lựa chọn hợp lý

Không phải quan hệ nào cũng nên expand. Một response có thể chỉ trả link:

~~~json
{
  "id": "ord-101",
  "status": "CONFIRMED",
  "links": {
    "self": "/api/orders/ord-101",
    "items": "/api/orders/ord-101/items"
  }
}
~~~

Client chỉ cần dữ liệu dòng hàng khi mở màn hình chi tiết sẽ gọi endpoint con. Link không tự cấp quyền: request tới /api/orders/ord-101/items **vẫn phải xác thực/phân quyền lại**.

Một API có thể dùng link và expand kết hợp: default trả link, expand nhúng một representation tối giản. Đây là cách cân bằng giữa số request và chi phí payload, không nhất thiết phải dùng một cơ chế truy vấn đồ thị tùy ý.

## 12. Tài liệu hóa bằng OpenAPI

Một API tốt không bắt client đoán trường hợp lệ hoặc cú pháp của expand. Mẫu OpenAPI 3.x rút gọn dưới đây mô tả các tham số query CSV; không tuyên bố response là chuẩn JSON:API.

~~~yaml
paths:
  /api/orders:
    get:
      summary: List visible orders with optional sparse fields and expansion
      parameters:
        - name: fields
          in: query
          required: false
          description: >
            Comma-separated scalar fields of the root order.
            id is always present in the response.
          style: form
          explode: false
          schema:
            type: array
            uniqueItems: true
            items:
              type: string
              enum: [id, status, totalAmount, createdAt]
          example: [id, status, totalAmount]
        - name: expand
          in: query
          required: false
          description: >
            Comma-separated allowlisted relationship paths.
            items.product implies items. Maximum depth is 2.
            Expansion budget is 5 points.
          style: form
          explode: false
          schema:
            type: array
            uniqueItems: true
            items:
              type: string
              enum: [customer, items, items.product]
          example: [customer, items.product]
        - name: limit
          in: query
          required: false
          schema:
            type: integer
            minimum: 1
            maximum: 50
            default: 20
        - name: cursor
          in: query
          required: false
          schema:
            type: string
          description: Opaque pagination token issued by the server
      responses:
        '200':
          description: Authorized page of orders
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderCollection'
        '400':
          description: Invalid query selection, limit, cursor, or syntax
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '401':
          description: Missing or invalid authentication
        '403':
          description: Insufficient permission to query requested data
components:
  schemas:
    OrderCollection:
      type: object
      required: [data, page]
      properties:
        data:
          type: array
          items:
            $ref: '#/components/schemas/OrderPreview'
        page:
          type: object
          properties:
            limit:
              type: integer
            nextCursor:
              type: string
              nullable: true
    OrderPreview:
      type: object
      required: [id]
      properties:
        id:
          type: string
        status:
          type: string
        totalAmount:
          type: integer
        createdAt:
          type: string
          format: date-time
        customer:
          $ref: '#/components/schemas/CustomerPreview'
        items:
          type: array
          items:
            $ref: '#/components/schemas/ItemPreview'
    CustomerPreview:
      type: object
      properties:
        id:
          type: string
        displayName:
          type: string
    ItemPreview:
      type: object
      properties:
        id:
          type: string
        quantity:
          type: integer
    ApiProblem:
      type: object
      properties:
        type:
          type: string
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
~~~

Đây là **mẫu minh họa**, chưa đủ schema cho product preview, JWT security scheme, ETag, các lỗi phân quyền phức tạp, link rel và ví dụ response đầy đủ. Với OpenAPI 3.0, cú pháp nullable: true hợp lệ; nếu dùng OpenAPI 3.1, thể hiện null bằng JSON Schema tương ứng. API thực cần nêu phiên bản và có test hợp đồng sinh client.

### 12.1. Những gì OpenAPI không tự chứng minh

Schema không tự thực thi:

- Ngân sách expansion (ví dụ customer=1 và items.product=4).
- Phân quyền theo tenant, từng resource và từng field.
- Giới hạn fan-out thực tế, DB timeout và query cost.
- Độ đúng của cursor gắn với filter/sort.
- Cache key cho từng shape và quyền.

Các quy tắc này phải được **ghi thành mô tả rõ và kiểm thử trong runtime**. Không nên dựa vào enum của schema để bảo đảm an toàn truy cập dữ liệu.

### 12.2. Khả năng mở rộng cú pháp trong tương lai

Một số API hỗ trợ fieldsets theo loại resource, ví dụ fields[orders]=id,status và fields[customers]=id,displayName, hoặc dùng include thay expand. Đó là những **hợp đồng khác**, thường thấy trong hệ sinh thái JSON:API hoặc API tự thiết kế.

Khi bổ sung selection cho object lồng nhau, cần quy định:

1. Cách phân biệt tên resource type và tên quan hệ.
2. Mỗi loại resource có allowlist và quyền riêng.
3. Trường bắt buộc và ID được giữ ra sao.
4. Nếu fields loại bỏ một relationship nhưng expand vẫn yêu cầu, bên nào có ưu tiên?
5. Chi phí, cache và schema thay đổi thế nào?

**Đừng âm thầm trộn nhiều cú pháp** vào một endpoint và để mỗi client diễn giải khác nhau. Quy tắc hiện tại của bài là fields cấp order, expand quan hệ và nested previews mặc định.

## 13. Kiểm thử hợp đồng fields/expand

### 13.1. Ma trận kiểm thử hành vi

| Request / tình huống | Kỳ vọng | Điều phải xác minh thêm |
|---|---|---|
| GET /orders không fields, không expand | 200, tập trường mặc định, không nhúng quan hệ | id luôn có; không lộ internal fields |
| fields=status,totalAmount | 200, thêm id, chỉ hai trường đã chọn và id | createdAt vắng mặt |
| fields=id,id,status | 200, không nhân đôi trường | Canonicalization nhất quán |
| fields= | 400 | Không diễn giải ngầm thành mọi trường |
| fields=id,,status | 400 | CSV trống bị phát hiện |
| fields=id,paymentToken | 400 hoặc chính sách che giấu tương ứng | Không công bố paymentToken |
| expand=customer | 200 với customer preview được phép | Không trả PII không được cấp quyền |
| expand=items.product | 200 với items và product preview | Depth và parent expansion đúng |
| expand=customer,items.product | 200 khi chi phí = 5 | Không cộng parent items hai lần |
| expand=items.product.supplier | 400 | Depth vượt giới hạn |
| expand=payments.card | 400 | Quan hệ không nằm allowlist |
| limit=0 / limit=51 | 400 | Phạm vi 1–50 |
| limit=abc | 400 | Conversion exception map đúng lỗi query |
| Token thiếu / hết hạn | 401 theo security contract | Không truy vấn dữ liệu nhạy cảm |
| Caller thiếu quyền xem fields hoặc expand | 403 hoặc lỗi che giấu đã thống nhất | Không rò rỉ tên trường và dữ liệu |
| Order thuộc tenant khác | Không được xuất hiện trong collection | Truy vấn tenant/ACL được áp dụng |
| Cursor của tenant khác | 400/403 theo chính sách token | Không dùng token để xem data liên tenant |
| Cursor với filter/sort không tương thích | Từ chối hoặc reset theo hợp đồng | Không trộn các trang thuộc query khác nhau |
| Expand trên nhiều order có hàng nghìn items | Từ chối/giới hạn theo contract | Không trả dữ liệu bị cắt âm thầm |
| Quan hệ optional không tồn tại | null/omitted theo schema | Không làm collection chính biến mất ngoài ý muốn |

Không chỉ test status; phải so **đúng các key trong JSON**, dữ liệu của từng tenant, số dòng và logic pagination.

### 13.2. Unit test bộ phân tích query

Ví dụ JUnit 5 dùng trực tiếp kiểu OrderReadShape phía trên:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OrderReadShapeTest {

    @Test
    void addsMandatoryIdToSparseFields() {
        OrderReadShape shape =
                OrderReadShape.parse(
                        "status,totalAmount", null, 20, null);

        assertTrue(shape.fields().contains("id"));
        assertTrue(shape.fields().contains("status"));
        assertTrue(shape.fields().contains("totalAmount"));
        assertFalse(shape.fields().contains("createdAt"));
    }

    @Test
    void normalizesNestedExpansion() {
        OrderReadShape shape =
                OrderReadShape.parse(
                        "id", "customer,items.product", 20, null);

        assertTrue(shape.expands().contains("items"));
        assertTrue(shape.expands().contains("items.product"));
        assertTrue(shape.expands().contains("customer"));
    }

    @Test
    void rejectsForbiddenSelection() {
        assertThrows(InvalidQueryShapeException.class,
                () -> OrderReadShape.parse(
                        "id,paymentToken", null, 20, null));
    }

    @Test
    void rejectsDeepExpansion() {
        assertThrows(InvalidQueryShapeException.class,
                () -> OrderReadShape.parse(
                        "id", "items.product.supplier", 20, null));
    }

    @Test
    void rejectsOutOfRangeLimit() {
        assertThrows(InvalidQueryShapeException.class,
                () -> OrderReadShape.parse(
                        null, null, 51, null));
    }
}
~~~

Các test parser chỉ chứng minh **allowlist và normalized shape**, chưa chứng minh dữ liệu trả đúng, truy vấn tối ưu hoặc quyền. Chúng cần được bổ sung bằng integration test và các phép đo query count.

### 13.3. Kiểm thử với MockMvc

Ví dụ fragment dưới đây giả định đã cấu hình MockMvc, security và dữ liệu/AuthorizedOrdersQuery ở môi trường test:

~~~java
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;

// Bên trong lớp test có trường mockMvc được inject:
@Test
void unknownExpansionReturns400() throws Exception {
    mockMvc.perform(get("/api/orders")
            .queryParam("fields", "id,status")
            .queryParam("expand", "payments.card"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.status").value(400))
        .andExpect(jsonPath("$.code")
                .value("INVALID_QUERY_SHAPE"));
}
~~~

Nếu endpoint yêu cầu xác thực, test phải đưa principal/token hợp lệ bằng cơ chế test của Spring Security; nếu không, request có thể bị chặn 401 **trước** khi vào parser. Đó là hành vi hợp lệ cần test riêng, không sửa cấu hình production chỉ để test 400 thuận tiện.

Thử nghiệm dữ liệu quan trọng hơn:

- Với caller tenant A, response **không chứa order tenant B** dù client gửi fields/expand bất kỳ.
- Với expanded customer, các trường nội bộ như riskScore, phonePrivate, passwordHash **không xuất hiện**.
- Khi client đổi fields, representation chỉ có key đã cho phép cộng id và các key quan hệ được expand.
- Với expand=items.product, thứ tự items và số lượng/giá snapshot đúng nghiệp vụ.
- ETag/304 không trả representation cũ khi expanded customer thay đổi hoặc quyền bị thu hồi.
- nextCursor giữ đúng filter/sort/query context; số order mỗi trang không bị ảnh hưởng bởi JOIN items.

### 13.4. Kiểm thử N+1 và giới hạn chi phí

Một integration test dữ liệu thật có thể chuẩn bị 1, 10, 20 và 50 order với số item khác nhau, chạy cùng expand=items.product và đo:

| Chỉ số | Điều cần xem |
|---|---|
| SQL statement count | Có tăng tuyến tính theo từng order hoặc item không? |
| Rows read | Có bị nhân khi JOIN nhiều collection không? |
| DB latency | Query có bị chậm ở tenant lớn hoặc dữ liệu lệch phân bố? |
| p95/p99 endpoint | Có đạt SLO ở limit 50 và expand nặng không? |
| Serialized bytes | Response có vượt payload budget? |
| CPU/memory app | Mapping/serialization có tăng bất thường không? |
| Authorization correctness | Quan hệ ngoại tenant không bị lộ |
| Cache behavior | Các query shape và tenant không trộn kết quả |

**Tránh test kiểu “SQL count bắt buộc luôn bằng 3”** nếu hệ thống có nhiều phiên bản DB/ORM và nhu cầu query hợp lệ khác nhau. Quan trọng là query count có tăng theo N ngoài dự kiến, tổng thời gian và số hàng đọc có chấp nhận được, cùng kết quả đúng. Có thể đặt ngưỡng hồi quy theo đường cơ sở đã đo.

### 13.5. Kiểm thử thủ công bằng curl

~~~bash
curl -i -G 'https://api.example.test/api/orders' \
  -H 'Authorization: Bearer <test-token>' \
  -H 'Accept: application/json' \
  --data-urlencode 'fields=id,status,totalAmount' \
  --data-urlencode 'expand=customer,items.product' \
  --data-urlencode 'limit=20'
~~~

Dùng tùy chọn **-G** cùng **--data-urlencode** để truyền các tham số qua query string và encode phù hợp. Token, URL và dữ liệu trong ví dụ chỉ mang tính minh họa; chỉ thử trên môi trường đã được phép. Không chia sẻ log chứa Authorization hoặc dữ liệu cá nhân.

## 14. Đánh giá kỹ thuật khi mở rộng quan hệ lớn

### 14.1. Giới hạn thời gian xử lý

Ngay cả request hợp lệ về mặt syntax vẫn có thể quá tốn kém ở runtime vì một tenant có nhiều orders/items. Kết hợp:

- Quota hoặc rate limit theo caller/tenant.
- Limit tối đa cho root collection.
- Giới hạn số phần tử của từng quan hệ; phân trang endpoint con khi cần.
- Timeout và ngân sách truy vấn phù hợp.
- Query cost estimate theo shape, kết hợp kiểm soát query plan/metrics.
- Giới hạn payload size và concurrency; backpressure khi tải vượt năng lực.

**Không coi HTTP 200 là thành công chất lượng** nếu request mất hàng chục giây và làm DB cạn tài nguyên. Mục tiêu là giữ response trong SLO và tránh làm ảnh hưởng caller khác.

### 14.2. Giới hạn độ dài query và số tham số

Một query string quá dài với hàng trăm tên field hoặc relation có thể bị từ chối ở reverse proxy trước khi đến Spring. API nên đặt giới hạn và mô tả lỗi phù hợp, thay vì giả định mọi HTTP client/gateway hỗ trợ URI vô hạn.

Đừng sử dụng GET body để né giới hạn URI một cách tùy tiện; ngữ nghĩa và khả năng tương tác của GET content không thống nhất rộng như query parameter. Với nhu cầu truy vấn biểu đạt phức tạp, có thể cân nhắc một tài nguyên tìm kiếm hoặc endpoint chuyên dụng theo hợp đồng rõ ràng.

### 14.3. Khi nào nên dùng read model hoặc endpoint chuyên dụng?

Nếu một màn hình dashboard cần tính 20 aggregate, dữ liệu nhiều nguồn và nested collection lớn, việc cố nhét mọi thứ vào expand có thể tạo API khó kiểm soát. Các lựa chọn:

- Tạo **read model** tối ưu cho báo cáo; ghi rõ độ trễ đồng bộ.
- Endpoint tổng hợp dành cho một use case có nhu cầu ổn định.
- Liên kết sang endpoint con có phân trang và khả năng cache độc lập.
- Tách query path khỏi transactional write path nếu workload và kiến trúc đòi hỏi.

Không nhất thiết tạo một endpoint cho mỗi màn hình. Chọn theo tần suất dùng, độ ổn định của hợp đồng, nhu cầu performance và khả năng vận hành.

### 14.4. Cân nhắc GraphQL, nhưng không dùng để né quản trị query

GraphQL cho client chọn shape phong phú hơn, nhưng vẫn cần **schema authorization, query complexity limit, depth limit, batching, caching, rate limit và observability**. Một REST API có fields/expand giới hạn thường đủ cho nhu cầu quen thuộc và đơn giản hơn khi vận hành. Không dùng GraphQL chỉ vì muốn tránh thiết kế allowlist quan hệ hoặc xử lý N+1.

## 15. Quan sát và vận hành endpoint có query shape

Khi triển khai production, theo dõi:

| Metric hoặc log | Mục tiêu |
|---|---|
| Request count theo route và mã lỗi | Phát hiện 400 do client dùng fields/expand sai |
| Top query shapes đã chuẩn hóa | Biết tổ hợp phổ biến để tối ưu/caching |
| p50/p95/p99 theo shape cost bucket | Phát hiện expand nặng làm chậm SLO |
| SQL count, rows scanned, DB wait | Tìm N+1, Cartesian explosion và thiếu index |
| Response bytes và serialization time | Đo ảnh hưởng của nested collection |
| 401/403/404 và policy denials | Phát hiện truy vấn không có quyền, enumeration |
| Cursor invalid/expired | Đo lỗi tương thích hoặc client giữ token quá lâu |
| Cache hit/miss theo biến thể | Đánh giá fragmentation và nguy cơ cache sai |
| Cost per request / theo tenant | Xác định shape gây tải không tương xứng |

Nên ghi **danh sách fields/expand đã chuẩn hóa** hoặc một mã shape đã phân loại, không log nguyên query nếu chứa PII, cursor nhạy cảm hay dữ liệu bí mật. Tránh gắn user ID, raw cursor, request ID duy nhất thành label metrics có cardinality quá cao.

Một chỉ số hữu ích là tỷ lệ **mở rộng nặng nhưng dữ liệu nhúng không được client tiêu thụ**; tuy nhiên server thường không nhìn thấy việc UI dùng trường nào, nên chỉ đo bằng telemetry phía client đã được phép hoặc phân tích theo hành trình nghiệp vụ.

### 15.1. Quy trình xử lý sự cố N+1

1. Tìm đường gọi có p99 tăng hoặc số query tăng theo kích thước trang.
2. Quan sát trace của một request với expand cụ thể.
3. Đếm SQL statements, rows, duration và wait; kiểm tra query plan.
4. Xác định nơi mapper/serializer chạm lazy relationship.
5. Batch-load hoặc đổi projection, vẫn giữ scope/ACL và pagination root.
6. Chạy lại cùng workload, dataset và shape; so sánh latency, DB load và đúng dữ liệu.
7. Bổ sung regression test và metric cảnh báo.

Đừng giải quyết một N+1 bằng cách chuyển mọi quan hệ sang **EAGER** không giới hạn. Điều đó có thể làm những request không expand vẫn tải toàn bộ quan hệ và tạo bottleneck mới.

## 16. Bài tập thực hành

### Bài 1 — Chọn fieldset

API công bố trường gốc id, status, totalAmount, createdAt; id luôn trả. Hãy viết URL lấy 10 order chỉ có id và status, không mở rộng quan hệ.

**Gợi ý:** GET /api/orders?fields=id,status&limit=10. Với fields=status&limit=10, theo hợp đồng này id cũng tự có mặt. Không kỳ vọng createdAt hoặc customer xuất hiện.

### Bài 2 — Chuẩn hóa expand

Người dùng gửi expand=items,items.product,customer. Với bảng cost đã cho, yêu cầu có hợp lệ không và chi phí là bao nhiêu?

**Đáp án:** Hợp lệ theo ví dụ, vì items.product đã bao hàm items, tính 4 điểm cho nhánh items.product và 1 điểm cho customer → 5 điểm, không phải 2+4+1=7. Các runtime guardrail khác như fan-out/response size vẫn có hiệu lực.

### Bài 3 — Phát hiện rủi ro N+1

Một trang trả 50 order. Mỗi order có 12 item. ORM chạy 1 SQL lấy order, 50 SQL lấy items theo order, và 600 SQL lấy product theo từng item.

**Câu hỏi:** Nguyên nhân, hệ quả và cách cải thiện?

**Gợi ý:** Có N+1 ở hai tầng. Phân trang 50 order trước, query items theo tập order ID trong batch, query product theo tập product ID trong batch, map theo ID, kiểm tra quyền, và đo SQL count/latency trước–sau. Nếu nhiều item trùng product, cache map theo product ID sẽ giảm truy xuất trùng lặp.

### Bài 4 — Fields và phân quyền

Caller thuộc tenant A có orders.read, gửi fields=id,internalNotes&expand=customer. internalNotes là trường nội bộ; customer liên quan có thông tin PII. Có nên trả nội dung đó nếu query SQL lấy được không?

**Đáp án:** Không. fields không trao quyền. internalNotes ngoài allowlist nên bị từ chối; customer chỉ được nhúng dưới DTO công khai và ACL/scope thích hợp. Truy vấn phải giới hạn tenant, không dùng JSON serializer trực tiếp trên entity.

### Bài 5 — Phân trang với one-to-many JOIN

Một SQL JOIN orders và items, rồi LIMIT 20, trả ra chỉ ba order khác nhau do mỗi order có nhiều item.

**Câu hỏi:** API có đạt hợp đồng limit=20 orders không?

**Đáp án:** Không. LIMIT 20 đang áp dụng cho hàng JOIN, không phải 20 root order. Cần lấy trang orders trước với sort/cursor ổn định, rồi tải items/product của các order trong trang đó.

### Bài 6 — ETag của expanded representation

Client đã cache GET /api/orders?fields=id,status&expand=customer với ETag tính chỉ từ order.version. Customer đổi displayName nhưng order.version không đổi.

**Câu hỏi:** Trả 304 có chắc đúng không?

**Đáp án:** Không. Representation được expand đã đổi; validator phải bao phủ các dữ liệu chi phối representation và quyền hiện hành, hoặc server phải vô hiệu hóa cache. Một ETag chỉ dựa vào order.version có thể gây 304 sai.

### Bài 7 — Thiết kế phản hồi cho quan hệ quá lớn

Một order có 50.000 dòng hàng, trong khi API chỉ hỗ trợ limit=50 order và expand=items. Server dự định tự cắt items còn 100 dòng nhưng không báo gì.

**Câu hỏi:** Cách này đúng không và nên thay thế bằng gì?

**Gợi ý:** Sai vì client có thể tưởng đã nhận toàn bộ items. Có thể từ chối expand, cung cấp endpoint /api/orders/{id}/items có phân trang, hoặc trả rõ hasMore/next link theo contract. Root limit=50 không giải quyết giới hạn của nested collection.

### Bài 8 — Thiết kế chính sách client

Hai client yêu cầu cùng route: mobile chỉ dùng id/status và web quản trị cần customer/items. Hãy chọn chiến lược cache, limit và theo dõi hiệu năng.

**Gợi ý:** Dùng fieldset/expansion theo nhu cầu, chặn các quan hệ nhạy cảm, chọn no-store cho order private, giới hạn limit và fan-out. Đo p95/p99/DB query count theo shape cost; nếu workload quản trị thường xuyên cần dữ liệu nặng, cân nhắc endpoint/read model chuyên biệt.

## 17. Checklist thiết kế trước khi phát hành

- [ ] Đã xác định trường scalar gốc nào được phép chọn và tập trường mặc định?
- [ ] Đã nói rõ id có bắt buộc và được thêm tự động hay không?
- [ ] Đã định nghĩa quan hệ allowlist, nested defaults, cú pháp expand và độ sâu tối đa?
- [ ] Đã đặt limit, giới hạn fan-out/payload và ngân sách chi phí mở rộng?
- [ ] Có hành vi thống nhất cho trường không hỗ trợ, tham số rỗng, trùng tên và cú pháp sai?
- [ ] Không dùng raw field/expand trong câu SQL, reflection hoặc serialization entity không kiểm soát?
- [ ] Đã kiểm tra quyền ở resource, field, relationship và tenant/ACL?
- [ ] Quan hệ chứa PII hoặc dữ liệu thanh toán không được nhúng chỉ vì client yêu cầu?
- [ ] Đã phân trang root trước khi batch-load quan hệ one-to-many?
- [ ] Đã đo N+1, SQL count, rows read, DB latency và response bytes khi expand sâu?
- [ ] Có phân biệt snapshot trong đơn và dữ liệu product/customer hiện tại?
- [ ] Có quy tắc rõ khi quan hệ optional, đã xóa hoặc không có quyền đọc?
- [ ] Cursor gắn đúng filter/sort/query context, được kiểm tra phạm vi và hết hạn?
- [ ] Cache/ETag phân biệt representation theo fields/expand và quyền hiện tại?
- [ ] Không âm thầm cắt nested collection; nếu giới hạn, có trạng thái và link lấy tiếp?
- [ ] Đã ghi query parameters, giới hạn, status lỗi và schema trong OpenAPI?
- [ ] Có unit test parser, MockMvc, integration/contract test, security test và performance regression test?
- [ ] Metrics có giúp tìm những query shape nặng mà không ghi PII/cursor vào nhãn?

## 18. Kết luận

**Chọn trường trả về** cho phép client nhận đúng phần dữ liệu cần thiết; **mở rộng quan hệ có kiểm soát** cho phép nhúng một số dữ liệu liên quan để giảm vòng gọi API. Cả hai chỉ có giá trị khi đi kèm hợp đồng ổn định về **trường được phép, quan hệ được phép, độ sâu, số phần tử, chi phí, phân trang và cache**.

Trong REST API, fields và expand **không thay thế phân quyền** và không nên biến việc truy vấn tập hợp thành tải toàn bộ đồ thị ORM. Hãy bắt đầu từ tập bản ghi caller được phép thấy, phân trang root, batch-load quan hệ, tạo DTO công khai, kiểm soát cost và đo hiệu năng. Khi dùng cùng Java/Spring, OpenAPI, kiểm thử hợp đồng và telemetry, cách thiết kế này cân bằng được **tính linh hoạt của client với độ tin cậy, bảo mật và hiệu năng của hệ thống**.

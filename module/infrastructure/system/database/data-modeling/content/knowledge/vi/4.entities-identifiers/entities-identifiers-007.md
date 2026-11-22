# Định danh trong nhiều tổ chức và không gian tên

## Mục tiêu bài học

Sau bài này, bạn có thể giải thích vì sao một mã chỉ duy nhất trong phạm vi một tổ chức hoặc hệ thống; xác định **không gian tên (namespace)** và **bên cấp mã (issuer)** của một định danh; thiết kế cách lưu nhiều mã ngoài cho cùng một thực thể nội bộ; và tránh gộp nhầm hai đối tượng chỉ vì chúng có cùng một chuỗi mã.

Bạn cũng sẽ biết cách chọn khóa nội bộ, xác định phạm vi duy nhất, xử lý mã thay đổi hoặc được tái sử dụng, liên kết dữ liệu giữa nhiều tổ chức và kiểm chứng các quy tắc định danh trong database cũng như API.

## 1. Vì sao định danh cần có phạm vi?

Một chuỗi như `C-001` có thể là mã khách hàng trong hệ thống CRM của Công ty A, mã hợp đồng trong hệ thống của Công ty B hoặc mã sản phẩm trong một danh mục khác. Chỉ nhìn vào giá trị `C-001` không thể biết nó chỉ đối tượng nào.

**Định danh (identifier)** là giá trị được dùng để tham chiếu một đối tượng trong một phạm vi nhất định. Khi nói một định danh là duy nhất, luôn cần hỏi: duy nhất ở đâu, do ai cấp, cho loại đối tượng nào và trong khoảng thời gian nào?

Ví dụ:

| Bên cấp mã | Loại đối tượng | Giá trị | Phạm vi duy nhất |
|---|---|---|---|
| CRM của Công ty A | Khách hàng | C-001 | Trong CRM của Công ty A |
| ERP của Công ty B | Khách hàng | C-001 | Trong ERP của Công ty B |
| Danh mục sản phẩm | Sản phẩm | C-001 | Trong danh mục sản phẩm |
| Hệ thống cửa hàng | Đơn hàng | C-001 | Trong hệ thống cửa hàng |

Các giá trị giống nhau không có nghĩa là cùng một đối tượng. Ngược lại, một đối tượng ngoài đời có thể có nhiều mã khác nhau trong các hệ thống.

Nếu thiết kế database với giả định mọi mã đều duy nhất toàn cục, việc nhập dữ liệu từ tổ chức khác có thể gây xung đột khóa. Nếu tự động gộp hai hồ sơ chỉ vì mã trùng, hệ thống có thể làm sai quan hệ, lịch sử và quyền truy cập.

## 2. Không gian tên và bên cấp định danh

### 2.1. Không gian tên (namespace)

**Không gian tên** là phạm vi quy ước trong đó các tên hoặc định danh được diễn giải và quản lý. Nó cho biết giá trị thuộc hệ thống, tổ chức, miền nghiệp vụ hoặc chuẩn nào.

Một namespace có thể được xác định bởi:

- tổ chức phát hành;
- hệ thống nguồn;
- loại đối tượng;
- tenant hoặc đơn vị kinh doanh;
- chuẩn định danh;
- phiên bản hoặc khoảng thời gian hiệu lực khi quy tắc thay đổi.

Ví dụ, hai CRM khác nhau có thể đều cấp mã khách hàng tăng dần từ 1. Namespace giúp phân biệt:

- `crm.company-a.customer` + `1001`;
- `crm.company-b.customer` + `1001`.

Giá trị định danh nên được hiểu cùng namespace của nó. Trong nhiều thiết kế, khóa định danh thực tế là một bộ gồm namespace và giá trị, chứ không chỉ là một chuỗi đơn lẻ.

### 2.2. Bên cấp mã (issuer)

**Issuer** là tổ chức hoặc hệ thống có thẩm quyền tạo và quản lý định danh. Issuer quyết định quy tắc cấp mã, tính duy nhất, cách thay đổi, thu hồi hoặc tái sử dụng mã.

Ví dụ:

- CRM cấp mã hồ sơ khách hàng.
- Cơ quan nhà nước cấp mã đăng ký doanh nghiệp.
- Nhà cung cấp thanh toán cấp mã giao dịch của họ.
- Hệ thống kho cấp mã lô hàng.
- Dịch vụ định danh nội bộ cấp UUID cho các thực thể trong nền tảng.

Namespace và issuer liên quan nhưng không phải lúc nào cũng giống nhau. Một tổ chức có thể có nhiều namespace cho khách hàng, nhà cung cấp và hợp đồng. Một namespace cũng có thể được quản lý theo một chuẩn chung mà nhiều tổ chức tham gia.

Khi tích hợp, cần biết nguồn nào có quyền khẳng định mã là hợp lệ và mã có thể được tra cứu ở đâu. Một hệ thống nhận mã không tự động trở thành bên có quyền sửa hoặc cấp lại mã đó.

### 2.3. Phạm vi duy nhất (uniqueness scope)

Phạm vi duy nhất cho biết tập bản ghi nào không được có cùng định danh. Các phạm vi thường gặp:

- toàn hệ thống;
- một tổ chức;
- một tenant;
- một hệ thống nguồn;
- một loại đối tượng trong một hệ thống;
- một khoảng thời gian hoặc một phiên bản danh mục.

Ví dụ, mã nhân viên có thể duy nhất trong một công ty nhưng không duy nhất giữa các công ty con. Mã sản phẩm có thể duy nhất trong một catalog nhưng trùng ở catalog của đối tác.

Hãy mô tả quy tắc bằng câu đầy đủ: “Trong cùng tenant và cùng hệ thống nguồn, một mã khách hàng chỉ được gắn với tối đa một hồ sơ khách hàng đang có hiệu lực.” Câu này rõ hơn nhiều so với “customer_code là unique”.

## 3. Định danh nội bộ và định danh bên ngoài

Một hệ thống thường cần phân biệt định danh do chính nó quản lý với mã được cấp từ bên ngoài.

### 3.1. Định danh nội bộ (internal identifier)

Định danh nội bộ được hệ thống sử dụng để tham chiếu ổn định một thực thể trong mô hình của mình. Có thể dùng số nguyên tăng dần, UUID hoặc một dạng ID khác.

Ví dụ, database có thể cấp `customer_id = 8f...` làm khóa chính cho hồ sơ khách hàng. Khóa này không cần mang ý nghĩa với người dùng và không phụ thuộc vào mã CRM của đối tác.

Ưu điểm của định danh nội bộ:

- hệ thống kiểm soát việc cấp và bảo đảm phạm vi duy nhất của nó;
- mã nguồn ngoài có thể thay đổi mà không buộc phải đổi khóa chính;
- nhiều mã ngoài có thể cùng tham chiếu một thực thể nội bộ;
- các quan hệ nội bộ không phụ thuộc trực tiếp vào chính sách của hệ thống đối tác.

Một UUID được sinh đúng cách giúp giảm nguy cơ va chạm giữa các hệ thống, nhưng **không chứng minh hai ID đại diện cho cùng một người hoặc tổ chức ngoài đời**. Nếu CRM A và CRM B cùng lưu một khách hàng, mỗi hệ thống có thể cấp một UUID khác nhau cho hồ sơ của mình.

### 3.2. Định danh bên ngoài (external identifier)

Định danh bên ngoài được cấp bởi một tổ chức, hệ thống hoặc chuẩn khác. Nó hữu ích khi đối chiếu, đồng bộ và truy vết dữ liệu nguồn.

Ví dụ, một hồ sơ khách hàng nội bộ có thể liên kết với:

- mã khách hàng trong CRM;
- mã tài khoản trong hệ thống chăm sóc khách hàng;
- mã khách hàng do đối tác bán hàng cấp;
- mã định danh doanh nghiệp từ một cơ quan có thẩm quyền.

Các mã này không nhất thiết có cùng định dạng hoặc cùng mức độ tin cậy. Hãy lưu nguồn cấp và phạm vi của từng mã.

### 3.3. Vì sao không dùng một mã ngoài làm khóa chính?

Dùng trực tiếp mã CRM của đối tác làm khóa chính có thể tạo phụ thuộc:

- đối tác đổi hệ thống hoặc đổi quy tắc cấp mã;
- cùng một đối tác có nhiều tenant;
- mã bị tái sử dụng sau khi hồ sơ bị xóa;
- doanh nghiệp hợp nhất hai hệ thống nguồn;
- cần thêm nguồn dữ liệu thứ hai cho cùng thực thể.

Một khóa nội bộ ổn định kết hợp bảng ánh xạ định danh ngoài thường dễ tiến hóa hơn. Mã ngoài vẫn được giữ nguyên để đối chiếu nhưng không chi phối toàn bộ quan hệ nội bộ.

## 4. Biểu diễn một định danh có phạm vi

Có nhiều cách biểu diễn một định danh. Điều quan trọng là không làm mất namespace và quy tắc duy nhất.

### 4.1. Bộ thành phần định danh

Một mô hình tổng quát có thể xem định danh là bộ:

```text
Identifier = (issuer, namespace, entity_type, value)
```

Trong đó:

- **issuer:** bên cấp và quản lý mã;
- **namespace:** phạm vi hoặc hệ thống mà mã thuộc về;
- **entity_type:** loại đối tượng được nhận diện;
- **value:** giá trị mã.

Tùy nghiệp vụ, có thể bổ sung tenant, phiên bản, quốc gia hoặc thời gian hiệu lực. Không phải mọi hệ thống đều cần tất cả thành phần; chỉ thêm phần thực sự tham gia vào quy tắc duy nhất hoặc diễn giải.

Ví dụ:

~~~json
{
  "issuer": "company-a",
  "namespace": "crm.customer",
  "entityType": "customer",
  "value": "C-001"
}
~~~

Định danh này khác với `C-001` do ERP của Công ty B cấp.

### 4.2. Dùng URI hoặc tên namespace có cấu trúc

Một số hệ thống dùng chuỗi có tiền tố để biểu diễn namespace:

~~~text
urn:company-a:crm:customer:C-001
urn:company-b:erp:customer:C-001
~~~

Cách này giúp nhìn thấy nguồn và phạm vi trong một giá trị. Tuy nhiên, chuỗi ghép chỉ an toàn khi có quy tắc mã hóa và phân tách rõ ràng. Nếu giá trị thành phần có thể chứa dấu phân cách, cần encoding hoặc lưu từng phần trong các cột riêng.

URI/URN không tự làm cho định danh trở thành duy nhất toàn cầu. Tính duy nhất vẫn phụ thuộc vào quy tắc đặt tên, quyền quản lý namespace và việc các bên tuân thủ quy ước.

### 4.3. Không gian tên theo tenant và theo hệ thống nguồn

Trong nền tảng nhiều tenant, hai khách hàng ở hai tenant có thể cùng có mã `1001`. Có hai phạm vi khác nhau cần phân biệt:

- tenant là phạm vi dữ liệu của khách hàng sử dụng nền tảng;
- hệ thống nguồn là nơi cấp mã được nhập vào nền tảng.

Nếu một tenant kết nối hai CRM, mã `1001` từ CRM A và CRM B vẫn có thể khác nhau. Khi đó phạm vi định danh có thể là tổ hợp `tenant_id + source_system + entity_type + external_value`.

Đừng chỉ thêm `tenant_id` vì kiến trúc multi-tenant có nó. Hãy xác nhận chính xác issuer và phạm vi cấp mã; đôi khi source system đã bao gồm tenant, đôi khi không.

## 5. Thiết kế bảng ánh xạ định danh ngoài

Một thực thể nội bộ có thể có nhiều định danh ngoài. Thay vì thêm một cột cho mỗi hệ thống như `crm_id`, `erp_id`, `partner_id`, có thể dùng bảng liên kết.

Ví dụ mô hình quan hệ:

~~~sql
CREATE TABLE customers (
    customer_id UUID PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE source_systems (
    source_system_id BIGINT PRIMARY KEY,
    issuer_code VARCHAR(100) NOT NULL,
    namespace_code VARCHAR(150) NOT NULL,
    UNIQUE (issuer_code, namespace_code)
);

CREATE TABLE customer_external_identifiers (
    customer_id UUID NOT NULL REFERENCES customers(customer_id),
    source_system_id BIGINT NOT NULL REFERENCES source_systems(source_system_id),
    tenant_key VARCHAR(100) NOT NULL,
    external_value VARCHAR(200) NOT NULL,
    PRIMARY KEY (
        customer_id,
        source_system_id,
        tenant_key,
        external_value
    ),
    UNIQUE (
        source_system_id,
        tenant_key,
        external_value
    )
);
~~~

Ý nghĩa:

- `customers.customer_id` là định danh nội bộ ổn định.
- `source_systems` mô tả issuer và namespace.
- `customer_external_identifiers` ánh xạ một hoặc nhiều mã nguồn đến hồ sơ nội bộ.
- Ràng buộc UNIQUE ngăn một mã ngoài trong cùng source system và tenant được gán cho hai hồ sơ khách hàng khác nhau.
- Khóa chính ghép ngăn lặp lại cùng một liên kết trong bảng.

Nếu mã ngoài chỉ duy nhất trong một loại đối tượng, cần đưa loại đối tượng vào phạm vi duy nhất hoặc dùng bảng riêng như ví dụ dành cho customer. Nếu một source system có thể phát hành cùng chuỗi cho customer và supplier, không được dùng một UNIQUE thiếu entity type trên bảng định danh dùng chung.

Trong thiết kế tổng quát, cần cân nhắc cách bảo đảm khóa ngoại đến nhiều loại thực thể. Một cột `entity_type` cùng `entity_id` trong bảng polymorphic không tự có thể tham chiếu bằng khóa ngoại thông thường đến nhiều bảng. Có thể dùng bảng ánh xạ riêng theo từng loại thực thể, hoặc một mô hình supertype có khóa chung nếu phù hợp.

### 5.1. Một đối tượng, nhiều định danh

Ví dụ, hồ sơ khách hàng nội bộ `customer_id = 500` có thể được ánh xạ:

| Customer nội bộ | Issuer/namespace | Tenant | Mã ngoài |
|---|---|---|---|
| 500 | CRM-A / crm.customer | tenant-01 | C-001 |
| 500 | ERP-A / erp.customer | tenant-01 | 000734 |
| 500 | Partner-X / partner.buyer | tenant-01 | BUY-77 |

Ba mã ngoài cùng tham chiếu một hồ sơ nội bộ theo quy tắc đối chiếu đã được xác nhận. Không nên kết luận chúng cùng một chủ thể chỉ vì tên hoặc email giống nhau.

### 5.2. Một mã ngoài có thể đổi theo thời gian

Một số hệ thống nguồn cho phép đổi mã, tái sử dụng mã hoặc chuyển dữ liệu sang namespace mới. Nếu cần truy xuất lịch sử, bảng ánh xạ có thể bổ sung:

- `valid_from`: thời điểm mã bắt đầu có hiệu lực;
- `valid_to`: thời điểm mã hết hiệu lực;
- `recorded_at`: thời điểm hệ thống ghi nhận liên kết;
- `status`: active, retired, disputed;
- `source_reference`: bằng chứng hoặc mã bản ghi nguồn.

Khi đó, quy tắc duy nhất phải xét cả thời gian hiệu lực. Một mã có thể được dùng lại ở hai khoảng thời gian khác nhau nếu chính sách issuer cho phép; nhưng hai ánh xạ đang hiệu lực đồng thời không được xung đột nếu namespace cam kết duy nhất.

Ràng buộc không chồng lấn khoảng thời gian có thể cần exclusion constraint, trigger hoặc logic transaction tùy hệ quản trị. Một UNIQUE thông thường không thể diễn đạt mọi quy tắc thời gian.

## 6. Định danh không đồng nghĩa với nhận diện thực thể

Đây là điểm rất quan trọng khi hợp nhất dữ liệu nhiều tổ chức.

- **Định danh (identification):** biết một bản ghi được tham chiếu bằng mã nào trong namespace cụ thể.
- **Đối chiếu thực thể (entity resolution):** xác định hai hoặc nhiều hồ sơ có đại diện cho cùng một thực thể ngoài đời hay không.
- **Hợp nhất hồ sơ (record consolidation):** quyết định cách kết hợp dữ liệu sau khi đã có đủ căn cứ rằng các hồ sơ cùng đại diện cho một thực thể.

Có mã khác nhau không chứng minh là hai người khác nhau. Có cùng tên, địa chỉ hoặc email cũng không đủ để chứng minh là cùng một người.

### 6.1. Các mức độ đối chiếu

Có thể dùng những mức bằng chứng khác nhau:

1. **Khớp định danh có thẩm quyền:** cùng một mã trong namespace được issuer xác nhận là duy nhất và không tái sử dụng.
2. **Khớp theo quy tắc nghiệp vụ:** tổ hợp thuộc tính được tổ chức xác nhận đủ để đối chiếu, chẳng hạn mã đăng ký doanh nghiệp cùng quốc gia cấp.
3. **Khớp xác suất:** tên, địa chỉ, số điện thoại hoặc thuộc tính khác cho thấy khả năng cùng một thực thể nhưng chưa đủ chắc chắn.
4. **Chưa xác định:** dữ liệu không đủ hoặc mâu thuẫn; giữ riêng hồ sơ cho đến khi có thêm bằng chứng.

Với khớp xác suất, cần có ngưỡng, quy trình xem xét và khả năng đảo ngược. Không nên tự động gộp dữ liệu quan trọng chỉ dựa trên tên gần giống hoặc email trùng.

### 6.2. Lưu liên kết và bằng chứng

Nếu cần ghi nhận kết quả đối chiếu, có thể dùng bảng `entity_links` hoặc `identity_matches` với các trường như:

- hai hồ sơ được đối chiếu;
- namespace và mã nguồn của từng hồ sơ;
- loại quan hệ: same_as, possible_match, related_to;
- trạng thái: proposed, confirmed, rejected;
- phương pháp và bằng chứng;
- người hoặc dịch vụ xác nhận;
- thời điểm và lịch sử thay đổi.

Cách này giữ được sự khác biệt giữa “hai mã tham chiếu cùng một hồ sơ” và “hai hồ sơ được cho là cùng một đối tượng ngoài đời”. Hai ý đó có liên quan nhưng không giống nhau.

### 6.3. Tránh hợp nhất nhầm

Trước khi gộp hồ sơ, hãy kiểm tra:

- mã có cùng issuer và namespace không;
- issuer có cam kết duy nhất và không tái sử dụng không;
- hai hồ sơ có cùng loại đối tượng không;
- dữ liệu có cùng thời điểm và ngữ cảnh không;
- có bằng chứng mâu thuẫn không;
- việc gộp có ảnh hưởng quyền truy cập, consent hoặc dữ liệu nhạy cảm không;
- có thể khôi phục nếu kết luận sai không.

Trong môi trường nhiều tổ chức, việc hai đơn vị cùng nói về một người không đồng nghĩa họ được phép chia sẻ mọi thông tin về người đó. Quy tắc định danh phải đi cùng quy tắc quyền truy cập và mục đích sử dụng dữ liệu.

## 7. Các loại định danh và cách chọn

### 7.1. Khóa thay thế (surrogate key)

Khóa thay thế là ID do hệ thống tạo ra, không mang ý nghĩa nghiệp vụ trực tiếp, ví dụ số nguyên hoặc UUID.

Phù hợp khi:

- cần khóa ổn định độc lập với mã nguồn;
- nhiều namespace cùng tham chiếu một thực thể;
- thuộc tính nghiệp vụ có thể thay đổi;
- cần tích hợp dữ liệu từ nhiều tổ chức.

Khóa thay thế không tự giải quyết việc nhận diện cùng thực thể giữa các nguồn. Nó chỉ tạo định danh ổn định trong hệ thống đang quản lý khóa đó.

### 7.2. Khóa tự nhiên (natural key)

Khóa tự nhiên dùng thuộc tính có ý nghĩa nghiệp vụ để nhận diện, ví dụ mã đăng ký doanh nghiệp trong phạm vi cơ quan cấp và quốc gia cụ thể.

Chỉ dùng khi đã xác nhận:

- phạm vi duy nhất;
- cơ quan cấp và cách xác minh;
- quy tắc thay đổi hoặc thu hồi;
- quy tắc tái sử dụng;
- độ ổn định theo thời gian.

Email, số điện thoại, tên và địa chỉ thường không phải khóa tự nhiên ổn định cho mọi miền. Chúng có thể thay đổi, được chia sẻ, được tái sử dụng hoặc có cách chuẩn hóa khác nhau.

### 7.3. Định danh ghép (composite identifier)

Định danh ghép gồm nhiều thành phần, ví dụ:

```text
(tenant_id, source_system, entity_type, external_value)
```

Một thành phần có thể không đủ duy nhất, nhưng tổ hợp được issuer và nghiệp vụ xác nhận là duy nhất.

Không nên nhầm khóa ghép với một chuỗi ghép tùy tiện. Nếu lưu dưới dạng chuỗi, phải xử lý dấu phân cách, encoding, chuẩn hóa và phiên bản quy tắc. Trong database, lưu thành các cột riêng thường dễ ràng buộc và truy vấn hơn.

### 7.4. UUID và mã toàn cục

UUID có thể được sinh độc lập ở nhiều hệ thống với xác suất va chạm rất thấp khi dùng thuật toán phù hợp. Nó hữu ích để cấp ID mà không cần một bộ đếm trung tâm.

Tuy vậy:

- UUID của hai hồ sơ khác nhau không cho biết chúng có cùng đại diện ngoài đời không.
- UUID không tự chứa issuer, quyền sở hữu hoặc ngữ nghĩa nghiệp vụ.
- UUID không thay thế bảng ánh xạ khi cần giữ mã ngoài.
- Cần chọn phiên bản, cách sinh, cách truyền và cách hiển thị thống nhất.

Nếu cần định danh có thể phân giải hoặc chia sẻ qua tổ chức, có thể dùng URI/URN theo một quy tắc namespace được quản lý. Việc phân giải URI và việc xác định thực thể vẫn là hai vấn đề riêng.

## 8. Chuẩn hóa và so sánh giá trị định danh

Hai chuỗi có thể trông giống nhau nhưng khác ở mã Unicode, chữ hoa/chữ thường, dấu cách hoặc số 0 ở đầu. Ngược lại, hai chuỗi khác cách viết có thể được xem là cùng mã theo quy tắc của issuer.

Trước khi so sánh, phải biết quy tắc chuẩn hóa của namespace.

### 8.1. Các vấn đề thường gặp

- **Chữ hoa/chữ thường:** `abc-01` có tương đương `ABC-01` không?
- **Dấu cách:** có được bỏ khoảng trắng đầu/cuối không; khoảng trắng ở giữa có ý nghĩa không?
- **Unicode:** ký tự có dấu có thể có nhiều cách mã hóa tương đương.
- **Số 0 đầu:** `00123` có khác `123` không?
- **Dấu phân cách:** dấu gạch ngang hoặc dấu chấm có phải thành phần của mã không?
- **Mã quốc gia và vùng:** có cần giữ mã quốc gia cấp hoặc loại tổ chức không?
- **Phiên bản:** quy tắc định dạng mã có thay đổi theo thời gian không?

Không tự động xóa dấu, bỏ số 0 đầu hoặc chuyển mọi giá trị thành chữ hoa. Làm vậy có thể biến hai mã khác nhau thành một mã hoặc khiến việc tra cứu ngược nguồn bị sai.

### 8.2. Lưu giá trị gốc và giá trị chuẩn hóa

Nếu issuer cho phép chuẩn hóa, có thể lưu cả:

- **raw_value:** giá trị nhận được nguyên gốc;
- **normalized_value:** giá trị sau khi áp dụng quy tắc chuẩn hóa đã xác nhận;
- **normalization_rule_version:** phiên bản quy tắc;
- **source_payload/reference:** tham chiếu đến bằng chứng nguồn nếu cần.

Giá trị gốc hỗ trợ audit và gửi lại cho hệ thống nguồn. Giá trị chuẩn hóa hỗ trợ so sánh. Cần ràng buộc duy nhất trên trường chuẩn hóa trong đúng namespace nếu đó là quy tắc nghiệp vụ.

### 8.3. Kiểu dữ liệu

Mã định danh thường nên được lưu dưới dạng chuỗi nếu nó có số 0 đầu, ký tự chữ hoặc không dùng cho tính toán. Không nên lưu mã `000123` thành số nguyên 123 rồi mất định dạng ban đầu.

Kiểu dữ liệu và độ dài phải dựa trên hợp đồng với issuer. Nếu mã có thể dài hơn dự kiến, cần quản lý việc mở rộng schema và validation.

## 9. Tích hợp nhiều tổ chức và tenant

Khi dữ liệu đi qua nhiều tổ chức, cần phân biệt quyền cấp mã, quyền sở hữu dữ liệu và quyền tham chiếu.

### 9.1. Một tổ chức có nhiều hệ thống nguồn

Một doanh nghiệp có thể dùng CRM, ERP, hệ thống hỗ trợ và nền tảng thương mại. Mỗi hệ thống có thể lưu hồ sơ khách hàng riêng và cấp ID riêng.

Cần xác định:

- hệ thống nào là nguồn chuẩn cho từng thuộc tính;
- mã nào dùng để đối chiếu;
- quan hệ giữa các hồ sơ nguồn;
- cách xử lý khi một hệ thống ngừng hoạt động hoặc thay thế;
- cách giữ lịch sử ánh xạ.

Không nhất thiết phải chọn một hệ thống làm nguồn chuẩn cho mọi trường. CRM có thể quản lý thông tin liên hệ, ERP quản lý mã thanh toán và hệ thống hóa đơn quản lý tên pháp lý.

### 9.2. Nhiều tổ chức chia sẻ một thực thể

Một nhà cung cấp có thể là đối tác của nhiều khách hàng doanh nghiệp. Mỗi doanh nghiệp có thể cấp mã nhà cung cấp riêng cho cùng một tổ chức ngoài đời.

Ví dụ:

| Tổ chức quản lý | Namespace | Mã nhà cung cấp |
|---|---|---|
| Công ty A | vendor-master-A | V-120 |
| Công ty B | vendor-master-B | SUP-88 |
| Công ty C | procurement-C | 00452 |

Nếu nền tảng quản lý danh mục đối tác dùng chung, nó có thể có một ID nội bộ cho tổ chức nhà cung cấp và nhiều ánh xạ mã theo từng công ty. Nhưng việc xác nhận các mã trên cùng chỉ một tổ chức cần bằng chứng phù hợp; không thể suy ra chỉ từ tên gần giống.

### 9.3. Cô lập tenant

Trong kiến trúc multi-tenant, dữ liệu một tenant phải được phân biệt và bảo vệ với tenant khác.

Một định danh có thể chỉ duy nhất trong tenant. Khi đó:

- mọi truy vấn cần áp dụng tenant context;
- khóa duy nhất phải chứa tenant nếu phạm vi là tenant;
- khóa ngoại và truy vấn phải ngăn tham chiếu chéo tenant ngoài ý muốn;
- cache key và message tích hợp cần mang tenant context phù hợp;
- log và audit phải ghi nhận phạm vi tổ chức.

Ví dụ ràng buộc:

~~~sql
CREATE TABLE tenant_customers (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    external_customer_code VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, external_customer_code)
);
~~~

Schema trên phù hợp khi mã ngoài duy nhất trong tenant và tenant chính là namespace cấp mã. Nếu mỗi tenant nhập từ nhiều nguồn có thể trùng mã, UNIQUE cần bổ sung source system hoặc namespace.

Cô lập tenant còn cần được bảo vệ ở tầng truy vấn, quyền database hoặc row-level security nếu hệ quản trị hỗ trợ. Chỉ đặt tenant_id trong bảng mà không kiểm tra mọi đường truy cập là chưa đủ.

## 10. Quản lý vòng đời của định danh

Định danh có thể được cấp, kích hoạt, đổi, thu hồi, hết hiệu lực hoặc tái sử dụng. Cần mô tả vòng đời thay vì chỉ lưu một giá trị hiện tại.

### 10.1. Đổi mã và mã thay thế

Khi hệ thống nguồn đổi mã khách hàng, không nên âm thầm ghi đè nếu mã cũ cần truy xuất. Hãy lưu mã mới, khoảng hiệu lực và quan hệ với mã cũ.

Một mã cũ có thể được giữ như alias hoặc historical identifier. API và báo cáo cần biết mã nào được chấp nhận để tra cứu và mã nào chỉ dùng cho lịch sử.

### 10.2. Thu hồi và tái sử dụng

Issuer có thể thu hồi mã hoặc tái sử dụng mã sau một khoảng thời gian. Cần phân biệt:

- mã chưa từng tồn tại;
- mã đang có hiệu lực;
- mã đã bị thu hồi;
- mã hết hiệu lực;
- mã được cấp lại cho đối tượng khác.

Nếu mã có thể được tái sử dụng, không được coi giá trị trần là định danh vĩnh viễn. Cần bổ sung thời gian hiệu lực, phiên bản hoặc ID bản ghi nguồn ổn định.

### 10.3. Hợp nhất và tách hồ sơ

Hai hồ sơ có thể được xác nhận là cùng một thực thể và cần hợp nhất. Ngược lại, một hồ sơ tổng hợp có thể phải tách thành hai đối tượng.

Hãy ghi lại:

- ID hồ sơ cũ và ID hồ sơ giữ lại;
- lý do và bằng chứng;
- thời điểm hợp nhất hoặc tách;
- cách chuyển các quan hệ phụ thuộc;
- cách xử lý định danh ngoài;
- cách truy xuất ID cũ;
- người hoặc quy trình phê duyệt.

Không nên xóa ID cũ khỏi lịch sử nếu hệ thống khác vẫn đang tham chiếu nó. Có thể duy trì bảng alias hoặc redirect để tra cứu, nhưng phải xác định cách xử lý ghi mới để tránh tiếp tục tạo liên kết vào hồ sơ đã ngừng sử dụng.

## 11. API và hợp đồng dữ liệu cho định danh

Khi định danh đi qua API, message hoặc file, hợp đồng phải nói rõ namespace và phạm vi duy nhất.

Một payload mơ hồ:

~~~json
{
  "customerId": "1001"
}
~~~

Người nhận không biết mã do ai cấp, thuộc tenant nào hay là ID nội bộ hay mã nguồn.

Payload rõ hơn:

~~~json
{
  "customer": {
    "internalId": "b4e6b0c0-0f2e-4a00-9d3f-21e3f2e9c123",
    "externalIdentifier": {
      "issuer": "company-a",
      "namespace": "crm.customer",
      "tenant": "tenant-01",
      "value": "1001"
    }
  }
}
~~~

Không phải mọi API đều cần gửi tất cả trường này. Nếu hợp đồng đã xác định tenant và issuer ở cấp request, có thể không lặp lại trong từng object. Nhưng bên nhận phải có đủ ngữ cảnh để diễn giải giá trị đúng.

### 11.1. Tránh nhầm tên trường

Các tên như `id`, `customerId`, `code`, `externalId` dễ gây nhầm. Hãy định nghĩa rõ:

- ID nội bộ hay ID nguồn;
- mã nghiệp vụ hay khóa database;
- namespace nào;
- có duy nhất toàn cục hay chỉ trong tenant;
- có được phép thay đổi không.

Không nên để API công khai khóa nội bộ nếu có lý do bảo mật hoặc khả năng thay đổi kiến trúc. Ngược lại, cũng không nên giả định UUID là bí mật; ID khó đoán không thay thế kiểm soát quyền truy cập.

### 11.2. Idempotency và định danh message

Khi tích hợp message, cần định danh sự kiện hoặc yêu cầu riêng với định danh thực thể. Một message có thể chứa:

- event_id: định danh duy nhất của message/sự kiện;
- entity_id: định danh đối tượng nội bộ hoặc nguồn;
- issuer/namespace: phạm vi của entity_id;
- occurred_at: thời điểm sự kiện xảy ra.

Idempotency key giúp nhận biết một yêu cầu hoặc message đã được xử lý, tránh tạo bản ghi trùng khi gửi lại. Không dùng customer_id làm idempotency key cho mọi thao tác vì một khách hàng có thể có nhiều sự kiện khác nhau.

## 12. Bảo mật và quyền riêng tư

Định danh có thể tiết lộ thông tin hoặc cho phép liên kết dữ liệu giữa các tổ chức. Một mã định danh doanh nghiệp công khai có thể ít nhạy cảm, trong khi mã tài khoản, số giấy tờ hoặc mã người dùng nội bộ có thể nhạy cảm hơn.

Khi thiết kế:

- chỉ chia sẻ định danh cần thiết cho mục đích tích hợp;
- tránh đưa thông tin cá nhân trực tiếp vào ID;
- không dùng ID khó đoán như cơ chế xác thực;
- giới hạn quyền tra cứu ánh xạ giữa mã ngoài và hồ sơ nội bộ;
- ghi audit cho thao tác liên kết, hợp nhất và tra cứu nhạy cảm;
- mã hóa hoặc bảo vệ các giá trị định danh theo phân loại dữ liệu;
- xác định thời hạn lưu và quy trình xóa/ẩn danh theo chính sách áp dụng.

Việc biết hai mã thuộc cùng một người có thể tự nó là thông tin nhạy cảm. Bảng ánh xạ định danh vì thế cần quyền truy cập phù hợp, không nên mặc định cho mọi dịch vụ đọc.

## 13. Kiểm chứng thiết kế định danh

Dùng các tình huống dưới đây để kiểm tra mô hình:

1. Hai tổ chức cùng cấp mã `C-001` cho hai khách hàng khác nhau.
2. Một tenant nhập mã `1001` từ hai hệ thống nguồn.
3. Một khách hàng có mã CRM, ERP và mã đối tác cùng lúc.
4. Hệ thống nguồn đổi mã nhưng cần truy xuất đơn hàng cũ.
5. Issuer tái sử dụng mã sau khi hồ sơ trước đã đóng.
6. Hai hồ sơ có cùng email nhưng khác mã định danh có thẩm quyền.
7. Một message được gửi lại nhiều lần.
8. Một tenant cố tham chiếu ID của tenant khác.
9. Hai hồ sơ được hợp nhất rồi sau đó phát hiện chúng là hai đối tượng khác nhau.
10. Quy tắc chuẩn hóa mã thay đổi và cần xử lý các giá trị cũ.

Với mỗi tình huống, kiểm tra:

- hệ thống xác định đúng namespace và issuer không;
- ràng buộc duy nhất có đúng phạm vi không;
- có tạo liên kết hoặc hợp nhất nhầm không;
- lịch sử định danh có được giữ không;
- dữ liệu có thể truy xuất và đối chiếu với nguồn không;
- quyền truy cập và cô lập tenant có được bảo vệ không;
- khi có lỗi, thao tác có thể được sửa hoặc đảo ngược an toàn không.

### 13.1. Checklist trước khi chốt mô hình

- [ ] Mỗi định danh có issuer và namespace được xác định.
- [ ] Loại thực thể và phạm vi duy nhất đã rõ.
- [ ] Phân biệt khóa nội bộ với mã ngoài.
- [ ] Quy tắc thay đổi, thu hồi và tái sử dụng được ghi nhận.
- [ ] Giá trị gốc và quy tắc chuẩn hóa được xác định.
- [ ] Nhiều mã ngoài có thể ánh xạ đến một thực thể theo chính sách rõ ràng.
- [ ] Quy trình đối chiếu thực thể có bằng chứng và trạng thái.
- [ ] Ràng buộc database ngăn trùng mã trong đúng phạm vi.
- [ ] API và message mang đủ ngữ cảnh định danh.
- [ ] Tenant isolation, quyền truy cập và audit được kiểm tra.

## 14. Những sai lầm thường gặp

- **Giả định mã duy nhất toàn cục:** mã có thể chỉ duy nhất trong một tổ chức hoặc namespace. Hãy xác định phạm vi trước khi tạo UNIQUE.
- **Dùng mã ngoài làm khóa nội bộ:** thay đổi ở hệ thống nguồn có thể lan đến mọi quan hệ. Hãy cân nhắc khóa nội bộ ổn định và bảng ánh xạ.
- **Coi UUID là danh tính toàn cầu:** UUID giúp tạo mã ít va chạm, nhưng không chứng minh hai hồ sơ là cùng một thực thể ngoài đời.
- **Gộp hồ sơ theo tên hoặc email:** thuộc tính có thể trùng hoặc thay đổi. Cần quy tắc đối chiếu và bằng chứng.
- **Bỏ tenant hoặc source system khỏi phạm vi duy nhất:** hai nguồn có thể cấp cùng một giá trị.
- **Chuẩn hóa quá mức:** xóa số 0 đầu hoặc dấu có thể làm biến đổi mã hợp lệ. Chỉ chuẩn hóa theo quy tắc issuer.
- **Ghi đè mã cũ:** làm mất khả năng truy xuất dữ liệu lịch sử và đối chiếu message cũ.
- **Dùng bảng polymorphic mà không bảo vệ tham chiếu:** cặp entity_type/entity_id không tự có khóa ngoại đến nhiều bảng.
- **Để lộ bảng ánh xạ cho mọi dịch vụ:** có thể tạo khả năng liên kết dữ liệu vượt quá quyền được cấp.
- **Dùng ID làm bằng chứng quyền truy cập:** biết ID không có nghĩa người gọi được phép đọc hoặc sửa đối tượng.

## 15. Kết luận

Một định danh chỉ có ý nghĩa khi biết giá trị đó do ai cấp, thuộc namespace nào, nhận diện loại đối tượng nào và duy nhất trong phạm vi nào. Trong môi trường nhiều tổ chức, cùng một chuỗi có thể hợp lệ ở nhiều hệ thống; một thực thể nội bộ cũng có thể cần giữ nhiều mã ngoài.

Hãy tách khóa nội bộ khỏi định danh nguồn khi cần, lưu ánh xạ cùng issuer và namespace, xác định quy tắc chuẩn hóa và vòng đời, đồng thời phân biệt việc tham chiếu một hồ sơ với việc xác nhận hai hồ sơ là cùng một thực thể ngoài đời. Những quy tắc này giúp tích hợp dữ liệu an toàn, truy xuất lịch sử và tiến hóa mô hình mà không làm mất ngữ nghĩa.

## Tự kiểm tra

1. Vì sao chuỗi `C-001` không đủ để nhận diện một khách hàng trong môi trường nhiều tổ chức?
2. Phân biệt issuer, namespace và uniqueness scope bằng ví dụ.
3. Vì sao UUID không giải quyết bài toán đối chiếu hai hồ sơ từ hai CRM?
4. Một tenant nhập mã khách hàng từ hai hệ thống nguồn. Ràng buộc UNIQUE cần gồm những thành phần nào?
5. Khi nào nên lưu cả raw_value và normalized_value?
6. Phân biệt định danh, entity resolution và hợp nhất hồ sơ.
7. Nếu issuer tái sử dụng mã sau khi hồ sơ đóng, cần bổ sung dữ liệu nào để truy xuất đúng lịch sử?
8. Hãy thiết kế bảng ánh xạ cho một thực thể trong hệ thống nhiều tenant, chỉ rõ issuer, namespace, khóa nội bộ, phạm vi duy nhất và quy tắc thay đổi mã.


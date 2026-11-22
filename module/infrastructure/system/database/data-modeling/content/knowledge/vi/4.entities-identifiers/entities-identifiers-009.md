# Phân biệt bản ghi trùng với hai thực thể có thuộc tính giống nhau

## 1. Vì sao phải phân biệt bản ghi trùng và thực thể khác nhau?

Trong quá trình thu thập và tích hợp dữ liệu, hệ thống có thể gặp hai tình huống nhìn bề ngoài rất giống nhau:

- Hai bản ghi mô tả **cùng một thực thể ngoài đời** nhưng được tạo hoặc nhập vào hệ thống nhiều lần.
- Hai bản ghi có một số hoặc thậm chí nhiều thuộc tính giống nhau, nhưng thực tế mô tả **hai thực thể khác nhau**.

Ví dụ, hai khách hàng cùng tên Nguyễn Minh Anh và cùng sinh ngày 12/04/1995 chưa chắc là một người. Ngược lại, một khách hàng có thể xuất hiện dưới tên “Nguyễn Minh Anh” ở hệ thống bán hàng và “Minh Anh Nguyen” ở hệ thống chăm sóc khách hàng, nhưng vẫn là cùng một người.

Nhầm hai tình huống này gây ra hai loại lỗi:

- **Gộp nhầm (false positive):** hai thực thể khác nhau bị coi là một. Dữ liệu của họ có thể bị trộn, quyền truy cập bị sai hoặc giao dịch bị gán cho nhầm người.
- **Bỏ sót trùng (false negative):** nhiều bản ghi của cùng một thực thể vẫn tồn tại riêng. Báo cáo có thể đếm một khách hàng nhiều lần, gửi thông báo lặp hoặc tạo hồ sơ không nhất quán.

Vì vậy, mô hình dữ liệu cần tách biệt khái niệm **bản ghi** (record), **thực thể** (entity) và **định danh** (identity). Bản ghi là cách hệ thống lưu một tập dữ liệu; thực thể là đối tượng hoặc sự việc mà dữ liệu đó mô tả; định danh là căn cứ để biết các bản ghi có đang nói về cùng một thực thể hay không.

## 2. Phân biệt giá trị thuộc tính giống nhau và danh tính giống nhau

### 2.1. Bằng nhau về thuộc tính không đồng nghĩa cùng một thực thể

Giả sử hệ thống lưu hai hồ sơ:

| Thuộc tính | Hồ sơ A | Hồ sơ B |
|---|---|---|
| Họ tên | Trần Minh An | Trần Minh An |
| Ngày sinh | 10/08/1990 | 10/08/1990 |
| Thành phố | Đà Nẵng | Đà Nẵng |
| Email | an.one@example.test | an.two@example.test |
| Mã hồ sơ | C-1001 | C-2048 |

Hai hồ sơ có cùng tên, ngày sinh và thành phố, nhưng có email và mã hồ sơ khác nhau. Điều đó chưa đủ để kết luận là hai người khác nhau, vì một người có thể dùng nhiều email. Nó cũng chưa đủ để kết luận là cùng một người. Cần thêm bằng chứng và hiểu biết về cách hệ thống cấp mã.

Một thuộc tính mô tả một khía cạnh của thực thể. Nhiều thực thể có thể chia sẻ cùng giá trị ở khía cạnh đó. Tên người, ngày sinh, tên sản phẩm phổ biến, địa chỉ tòa nhà hoặc mã vùng không nhất thiết duy nhất.

### 2.2. Khác nhau về thuộc tính cũng không nhất thiết là khác thực thể

Một thực thể có thể thay đổi theo thời gian. Khách hàng chuyển nhà, đổi số điện thoại, thay đổi họ tên hoặc cập nhật email. Nếu hai bản ghi khác nhau ở địa chỉ, không thể tự động kết luận chúng là hai khách hàng khác nhau.

Cần phân biệt:

- **Thuộc tính ổn định:** ít thay đổi và có thể hỗ trợ nhận diện, ví dụ mã định danh do cơ quan hoặc hệ thống có thẩm quyền cấp trong một phạm vi xác định.
- **Thuộc tính biến động:** có thể thay đổi theo thời gian, ví dụ địa chỉ, số điện thoại, email, trạng thái.
- **Thuộc tính dùng chung:** nhiều thực thể có thể có cùng giá trị, ví dụ họ tên, ngày sinh, thành phố hoặc tên sản phẩm.
- **Thuộc tính theo ngữ cảnh:** chỉ duy nhất trong một phạm vi, ví dụ mã nhân viên trong một công ty hoặc số phòng trong một tòa nhà.

Để xác định hai bản ghi có cùng thực thể hay không, phải xem xét ý nghĩa, độ ổn định, phạm vi và nguồn gốc của từng thuộc tính.

## 3. Bản ghi trùng là gì?

Bản ghi trùng (duplicate record) xảy ra khi nhiều hàng hoặc tài liệu cùng mô tả một thực thể hoặc một sự kiện theo quy tắc nghiệp vụ, dù chúng có thể khác nhau về cách biểu diễn hoặc một số thuộc tính.

Các nguyên nhân thường gặp:

- Người dùng tạo hồ sơ nhiều lần do không tìm thấy hồ sơ cũ.
- Một yêu cầu được gửi lại sau timeout nhưng thao tác tạo mới không có cơ chế idempotency.
- Dữ liệu được nhập từ nhiều file hoặc nhiều hệ thống nguồn.
- Một hệ thống đồng bộ lại dữ liệu nhưng không nhận diện được bản ghi đã tồn tại.
- Cùng một người được ghi nhận với cách viết tên, địa chỉ hoặc số điện thoại khác nhau.
- Quy tắc định danh thay đổi nhưng dữ liệu lịch sử chưa được hợp nhất.

Ví dụ, cùng một khách hàng có thể được ghi thành hai hồ sơ:

| customer_id | full_name | email | source |
|---|---|---|---|
| 501 | Nguyen Thi Mai | mai@example.test | Web |
| 892 | Mai Nguyen | MAI@example.test | CRM |

Nếu quy tắc chuẩn hóa email không phân biệt chữ hoa/thường và có bằng chứng hai hồ sơ thuộc cùng khách hàng, đây có thể là bản ghi trùng. Nhưng không nên gộp chỉ vì email giống nhau nếu hệ thống cho phép địa chỉ dùng chung hoặc email chưa được xác minh.

Bản ghi trùng không nhất thiết giống từng byte. Một bản ghi có thể thiếu số điện thoại, bản ghi kia có địa chỉ mới; một nguồn dùng dấu tiếng Việt, nguồn khác bỏ dấu. Việc nhận diện trùng cần hiểu dữ liệu và ngữ cảnh nghiệp vụ.

## 4. Hai thực thể khác nhau có thuộc tính giống nhau

Hai thực thể khác nhau có thể có cùng nhiều thuộc tính mô tả. Điều này đặc biệt phổ biến khi thuộc tính được chọn không có tính duy nhất.

Ví dụ:

- Hai người cùng họ tên, ngày sinh và thành phố.
- Hai sản phẩm cùng tên thương mại nhưng thuộc nhà sản xuất hoặc phiên bản khác nhau.
- Hai phòng có cùng mã “A101” nhưng ở hai tòa nhà khác nhau.
- Hai doanh nghiệp có cùng tên hiển thị nhưng khác mã số đăng ký.
- Hai giao dịch có cùng số tiền và thời điểm gần nhau nhưng được thực hiện bởi hai tài khoản khác nhau.

Để tránh gộp nhầm, cần xác định phạm vi định danh. Ví dụ, mã phòng chỉ duy nhất trong tòa nhà:

```sql
UNIQUE (building_id, room_code)
```

Hai phòng `A101` ở hai tòa nhà khác nhau là hai thực thể hợp lệ. Nếu chỉ đặt `UNIQUE(room_code)`, cơ sở dữ liệu sẽ từ chối dữ liệu hợp lệ. Nếu không có constraint phù hợp, hệ thống có thể liên kết sai phòng khi chỉ tìm bằng mã cục bộ.

### 4.1. Thực thể và bản ghi không có quan hệ một-một tuyệt đối

Một thực thể có thể có nhiều bản ghi do trùng lặp hoặc do lịch sử. Một bản ghi cũng có thể mô tả nhiều thực thể nếu mô hình gộp dữ liệu không đúng cách, ví dụ lưu hai người liên hệ trong một trường văn bản hoặc lưu nhiều thiết bị trong cùng một hàng mà không có định danh riêng.

Do đó, không nên suy ra danh tính chỉ từ số lượng hàng hoặc từ sự giống nhau của các cột. Mô hình cần xác định rõ đối tượng được quản lý, vòng đời của đối tượng và cách một bản ghi đại diện cho đối tượng đó.

## 5. Các loại định danh và vai trò của chúng

### 5.1. Định danh nội bộ

Định danh nội bộ (surrogate identifier) do hệ thống cấp, chẳng hạn `customer_id` hoặc UUID. Nó phân biệt các hồ sơ trong một hệ thống và thường ổn định trong suốt vòng đời bản ghi.

Ví dụ:

```sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(320)
);
```

Nếu hai hồ sơ có `customer_id` khác nhau, chúng là hai bản ghi khác nhau trong bảng. Tuy nhiên, điều này chưa chứng minh chúng là hai người khác nhau ngoài đời. Chúng có thể là hai bản ghi trùng được tạo độc lập.

Đây là điểm quan trọng: khóa chính đảm bảo nhận diện bản ghi trong cơ sở dữ liệu; nó không tự động chứng minh danh tính thực tế của đối tượng được mô tả.

### 5.2. Định danh nghiệp vụ

Định danh nghiệp vụ là mã được quy định bởi quy trình nghiệp vụ hoặc hệ thống có thẩm quyền, ví dụ mã số thuế, mã nhân viên, số hợp đồng hoặc mã khách hàng của một tổ chức.

Khi sử dụng, cần xác định:

- Ai cấp mã và có bao nhiêu nguồn cấp?
- Mã duy nhất trong toàn hệ thống hay chỉ trong tổ chức/đơn vị?
- Mã có thể thay đổi hoặc được tái sử dụng không?
- Mã có được xác minh hay chỉ do người dùng nhập?
- Có quy tắc chuẩn hóa trước khi so sánh không?

Một mã chỉ duy nhất trong một tổ chức phải được kết hợp với định danh tổ chức khi kiểm tra:

```sql
UNIQUE (organization_id, employee_code)
```

### 5.3. Định danh từ hệ thống nguồn

Khi hợp nhất nhiều hệ thống, mỗi nguồn có thể có mã riêng cho cùng một khách hàng. Không nên giả định mã nguồn là duy nhất toàn cục.

Có thể lưu ánh xạ định danh nguồn:

```sql
CREATE TABLE customer_source_id (
    source_system VARCHAR(50) NOT NULL,
    source_customer_id VARCHAR(100) NOT NULL,
    customer_id BIGINT NOT NULL,
    PRIMARY KEY (source_system, source_customer_id),
    FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
);
```

Khóa ghép `(source_system, source_customer_id)` phân biệt cùng một mã được cấp bởi các hệ thống khác nhau. Nhiều mã nguồn có thể ánh xạ đến một `customer_id` chuẩn sau khi đã xác minh chúng cùng mô tả một khách hàng.

Cấu trúc này giúp giữ lại nguồn gốc của dữ liệu và hỗ trợ truy vết khi phát hiện ghép nhầm.

## 6. Entity resolution: nhận diện các bản ghi cùng thực thể

Entity resolution (giải quyết định danh thực thể) là quá trình xác định những bản ghi nào mô tả cùng một thực thể, dù dữ liệu có thể khác nhau. Quá trình này còn được gọi là record linkage hoặc deduplication tùy ngữ cảnh.

Có thể chia thành các bước:

1. Chuẩn hóa các thuộc tính dùng để so khớp.
2. Tìm các cặp bản ghi có khả năng liên quan.
3. Tính mức độ phù hợp dựa trên nhiều thuộc tính và quy tắc.
4. Quyết định tự động ghép, yêu cầu con người xem xét hoặc giữ riêng.
5. Lưu kết quả, bằng chứng và lịch sử thay đổi để có thể truy vết.

### 6.1. Chuẩn hóa dữ liệu

Chuẩn hóa giúp giảm khác biệt hình thức không mang ý nghĩa nghiệp vụ. Ví dụ:

| Giá trị ban đầu | Giá trị chuẩn hóa minh họa |
|---|---|
| ` MAI.NGUYEN@EXAMPLE.TEST ` | `mai.nguyen@example.test` |
| `Nguyễn  Thị Mai` | `Nguyễn Thị Mai` |
| `+84 912 345 678` | `+84912345678` |
| `12 Đường Lê Lợi` | Chuỗi địa chỉ đã tách và chuẩn hóa theo quy tắc |

Không phải trường nào cũng có thể chuẩn hóa bằng cách chuyển chữ thường hoặc bỏ dấu. Ví dụ tên người cần giữ nguyên dạng gốc để hiển thị; số điện thoại cần chuẩn hóa theo mã quốc gia; địa chỉ cần xử lý thành phần địa giới; email có quy tắc so sánh phụ thuộc chính sách và semantics của hệ thống.

Nên lưu cả giá trị gốc và giá trị chuẩn hóa khi cần truy vết hoặc hiển thị chính xác.

### 6.2. So khớp chính xác và so khớp gần đúng

**Exact matching** so sánh giá trị sau chuẩn hóa hoặc định danh đã xác minh. Ví dụ, cùng một mã hợp đồng từ cùng hệ thống nguồn có thể là bằng chứng mạnh.

**Fuzzy matching** so sánh các giá trị gần giống nhau, chẳng hạn lỗi chính tả trong tên, khác biệt viết tắt hoặc biến thể địa chỉ. Các phương pháp có thể dùng gồm:

- Khoảng cách chỉnh sửa (edit distance) để đo số thao tác thêm, xóa hoặc thay thế ký tự.
- Jaro-Winkler để so sánh chuỗi tên có tiền tố giống nhau.
- Token similarity để so sánh các từ trong tên hoặc địa chỉ.
- So khớp ngày tháng trong một khoảng sai lệch được cho phép.
- So khớp số điện thoại hoặc email sau chuẩn hóa.

Không có một thuật toán fuzzy matching nào phù hợp cho mọi trường. Tên người, địa chỉ, mã sản phẩm và số định danh có semantics khác nhau. Ngưỡng so khớp phải được đánh giá trên dữ liệu thực tế đã gán nhãn.

### 6.3. Kết hợp nhiều thuộc tính

Không nên quyết định ghép chỉ dựa vào một thuộc tính phổ biến. Có thể kết hợp tên, ngày sinh, email, điện thoại, địa chỉ và định danh nguồn theo độ tin cậy của từng trường.

Ví dụ về bảng tiêu chí:

| Thuộc tính | Bằng chứng so khớp | Mức tin cậy tương đối |
|---|---|---|
| Mã định danh đã xác minh trong cùng phạm vi | Trùng chính xác | Rất mạnh |
| Email đã xác minh | Trùng sau chuẩn hóa | Mạnh, tùy chính sách dùng chung |
| Số điện thoại | Trùng sau chuẩn hóa | Trung bình đến mạnh, tùy khả năng tái sử dụng |
| Họ tên | Trùng chính xác hoặc gần đúng | Yếu đến trung bình |
| Ngày sinh | Trùng chính xác | Hỗ trợ, nhưng không đủ một mình |
| Địa chỉ | Trùng một phần hoặc gần đúng | Hỗ trợ, vì có thể dùng chung hoặc thay đổi |

Bảng chỉ là gợi ý tương đối. Độ tin cậy phụ thuộc chất lượng dữ liệu, nguồn cấp, quy trình xác minh và miền nghiệp vụ.

### 6.4. Điểm số và ngưỡng quyết định

Một hệ thống matching có thể tính điểm từ nhiều bằng chứng:

```text
Điểm phù hợp
  = w1 × điểm tên
  + w2 × điểm ngày sinh
  + w3 × điểm email
  + w4 × điểm điện thoại
  + w5 × điểm địa chỉ
```

Trong đó các trọng số `w1...w5` phản ánh mức tin cậy và tổng trọng số có thể được chuẩn hóa về 1. Đây chỉ là mô hình minh họa; trong hệ thống thực tế cần huấn luyện hoặc hiệu chỉnh trọng số dựa trên cặp dữ liệu đã được xác nhận.

Có thể chia kết quả thành ba vùng:

| Điểm/điều kiện | Hành động |
|---|---|
| Rất cao và có bằng chứng định danh mạnh | Tự động ghép theo chính sách đã kiểm chứng |
| Trung gian hoặc có tín hiệu mâu thuẫn | Chuyển người có thẩm quyền xem xét |
| Thấp | Giữ hai hồ sơ riêng |

Không nên chọn ngưỡng chỉ để giảm số lượng hồ sơ. Gộp nhầm có thể gây hậu quả nghiêm trọng hơn bỏ sót trùng, đặc biệt với hồ sơ y tế, tài chính, quyền truy cập hoặc dữ liệu cá nhân.

## 7. False positive và false negative

### 7.1. False positive: gộp hai thực thể khác nhau

Ví dụ hai người cùng tên và ngày sinh bị ghép thành một khách hàng. Hậu quả có thể gồm:

- Lịch sử mua hàng của người này hiển thị cho người kia.
- Hóa đơn, điểm thưởng hoặc khoản nợ bị gán sai.
- Quyền truy cập và thông báo bị gửi nhầm.
- Việc sửa hoặc xóa dữ liệu của một người ảnh hưởng đến người còn lại.

Để giảm false positive:

- Ưu tiên định danh có nguồn gốc và phạm vi rõ ràng.
- Không dùng tên hoặc địa chỉ làm khóa duy nhất nếu nghiệp vụ không bảo đảm.
- Xem xét các bằng chứng mâu thuẫn, ví dụ hai mã định danh đã xác minh khác nhau.
- Dùng ngưỡng tự động ghép thận trọng.
- Chuyển các trường hợp không chắc chắn cho người có thẩm quyền.
- Lưu lý do và bằng chứng của quyết định ghép.

### 7.2. False negative: bỏ sót bản ghi trùng

Ví dụ cùng một người có hai hồ sơ vì một hồ sơ ghi email cũ, hồ sơ kia ghi email mới; tên cũng khác cách viết. Hệ thống không phát hiện và tiếp tục tạo hai khách hàng.

Để giảm false negative:

- Chuẩn hóa giá trị trước khi so sánh.
- Kết hợp nhiều thuộc tính thay vì chỉ so khớp chính xác một trường.
- Sử dụng các khóa định danh từ nguồn khi có thể.
- Tìm kiếm các cặp ứng viên trong những nhóm dữ liệu có khả năng trùng.
- Cho phép người dùng báo cáo hồ sơ nghi trùng.
- Định kỳ rà soát các bản ghi mới và dữ liệu lịch sử.

Mục tiêu không phải xóa bỏ mọi khác biệt giữa bản ghi mà là đưa ra quyết định có căn cứ về danh tính.

## 8. Quy trình xử lý bản ghi trùng an toàn

### 8.1. Xác định quy tắc ghép trước khi hợp nhất

Trước khi cập nhật dữ liệu, cần xác định:

- Loại thực thể đang xử lý: khách hàng, sản phẩm, nhân viên, địa điểm hay sự kiện.
- Các thuộc tính được dùng để nhận diện và mức độ tin cậy của chúng.
- Phạm vi định danh: toàn cục, tenant, tổ chức, nguồn hoặc thời gian.
- Những thuộc tính nào có thể thay đổi.
- Trường hợp nào được tự động ghép và trường hợp nào cần duyệt.
- Hệ thống nào là nguồn dữ liệu có thẩm quyền cho từng thuộc tính.

Cùng một quy tắc không nhất thiết áp dụng cho mọi thực thể. Hai sản phẩm có cùng tên có thể là hai SKU khác nhau; hai giao dịch có cùng số tiền không phải là cùng giao dịch.

### 8.2. Chọn bản ghi chuẩn và hợp nhất thuộc tính

Khi đã xác nhận hai bản ghi cùng một thực thể, cần chọn một định danh chuẩn (canonical ID). Sau đó quyết định cách xử lý thuộc tính:

- Giữ giá trị từ nguồn có thẩm quyền.
- Ưu tiên giá trị đã xác minh.
- Giữ lịch sử thay đổi nếu giá trị có ý nghĩa theo thời gian.
- Ghi nhận nguồn và thời điểm cập nhật.
- Không ghi đè dữ liệu tốt bằng giá trị thiếu hoặc kém tin cậy.

Ví dụ, hồ sơ A có email đã xác minh, hồ sơ B có số điện thoại mới đã xác minh. Bản ghi chuẩn có thể giữ cả hai thuộc tính cùng nguồn gốc tương ứng, thay vì chọn toàn bộ dữ liệu từ một hồ sơ duy nhất.

### 8.3. Chuyển các quan hệ tham chiếu

Nếu hai customer record được hợp nhất, các đơn hàng, phiếu hỗ trợ, giao dịch và quan hệ khác phải tiếp tục tham chiếu đến khách hàng chuẩn.

Có thể duy trì bảng ánh xạ ID cũ sang ID chuẩn:

```sql
CREATE TABLE entity_id_redirect (
    entity_type VARCHAR(50) NOT NULL,
    old_entity_id BIGINT NOT NULL,
    canonical_entity_id BIGINT NOT NULL,
    merged_at TIMESTAMP NOT NULL,
    reason VARCHAR(500),
    PRIMARY KEY (entity_type, old_entity_id)
);
```

Bảng này giúp xử lý các tham chiếu cũ, truy vết quyết định và chuyển đổi dần các hệ thống tích hợp. Cần ngăn ánh xạ vòng lặp, ví dụ A trỏ B rồi B lại trỏ A; cũng cần bảo đảm ID chuẩn cuối cùng vẫn tồn tại và có trạng thái hợp lệ.

Việc cập nhật khóa ngoại phải được thực hiện trong giao dịch hoặc quy trình có kiểm soát, có khả năng khôi phục và tránh mất liên kết. Với dữ liệu lớn, có thể cần chia thành các batch và theo dõi tiến độ.

### 8.4. Không xóa dấu vết nguồn gốc

Sau khi hợp nhất, không nên xóa mọi dấu vết của bản ghi cũ nếu nghiệp vụ cần kiểm toán hoặc giải thích lịch sử. Nên lưu:

- ID cũ và ID chuẩn.
- Thời điểm, người hoặc tiến trình thực hiện ghép.
- Lý do và bằng chứng.
- Giá trị trước và sau khi hợp nhất nếu cần.
- Nguồn hệ thống của các thuộc tính.
- Cách xử lý các quan hệ liên quan.

Một quyết định ghép sai cần có cách hoàn tác hoặc tách lại (unmerge) khi chính sách và cấu trúc dữ liệu cho phép.

## 9. Ngăn bản ghi trùng ngay từ lúc ghi dữ liệu

### 9.1. Unique constraint theo quy tắc đã xác minh

Nếu nghiệp vụ có định danh duy nhất rõ ràng, hãy bảo vệ bằng ràng buộc ở cơ sở dữ liệu. Ví dụ, mã khách hàng duy nhất trong một tenant:

```sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_code VARCHAR(50) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    CONSTRAINT uq_customer_tenant_code
        UNIQUE (tenant_id, customer_code)
);
```

Constraint này ngăn hai bản ghi dùng cùng mã trong một tenant. Nó không ngăn hai khách hàng có cùng tên, vì tên không được xác định là duy nhất.

Chỉ thêm unique constraint khi nghiệp vụ thực sự yêu cầu. Nếu đặt `UNIQUE(full_name, birth_date)`, hệ thống có thể từ chối hai người khác nhau nhưng có cùng tên và ngày sinh.

### 9.2. Idempotency cho yêu cầu được gửi lại

Một nguyên nhân tạo bản ghi trùng là client gửi lại yêu cầu sau timeout mà không biết lần trước đã thành công hay chưa. Idempotency key giúp hệ thống nhận diện cùng một yêu cầu nghiệp vụ được gửi nhiều lần.

Ví dụ, với yêu cầu tạo thanh toán:

```sql
CREATE TABLE payment_request (
    request_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    payment_id BIGINT,
    CONSTRAINT uq_payment_request
        UNIQUE (tenant_id, idempotency_key)
);
```

Khi nhận yêu cầu, hệ thống kiểm tra khóa idempotency trong phạm vi tenant. Nếu khóa đã tồn tại, trả lại kết quả đã ghi nhận hoặc xử lý theo trạng thái trước đó, thay vì tạo giao dịch mới. Cần lưu cả kết quả và trạng thái xử lý để tránh hai yêu cầu đồng thời cùng tạo bản ghi.

Idempotency chống lặp lại cùng một yêu cầu; nó không giải quyết mọi trường hợp hai người dùng tạo hai yêu cầu khác nhau nhưng thực chất cùng một thực thể. Trường hợp đó vẫn cần quy tắc định danh và entity resolution.

### 9.3. Kiểm tra trước và constraint khi ghi

Ứng dụng có thể tìm kiếm hồ sơ tương tự trước khi tạo mới để cảnh báo người dùng. Tuy nhiên, kiểm tra trước không thay thế unique constraint vì hai yêu cầu đồng thời có thể cùng vượt qua bước kiểm tra.

Nên kết hợp:

- Kiểm tra trước để hỗ trợ trải nghiệm người dùng.
- Constraint ở cơ sở dữ liệu cho các quy tắc duy nhất chắc chắn.
- Quy trình matching cho các trường hợp cần so khớp gần đúng.
- Quy trình duyệt và hợp nhất cho trường hợp chưa đủ bằng chứng.

## 10. Đánh giá chất lượng quy trình nhận diện

Không nên chỉ đo số lượng bản ghi đã hợp nhất. Cần đánh giá chất lượng bằng dữ liệu được con người xác nhận hoặc bộ dữ liệu chuẩn.

Các chỉ số thường dùng:

- **Precision:** trong số cặp được hệ thống dự đoán là trùng, có bao nhiêu cặp thực sự trùng?
- **Recall:** trong số cặp thực sự trùng, hệ thống tìm được bao nhiêu cặp?
- **False positive rate:** tỷ lệ cặp khác thực thể bị dự đoán nhầm là trùng.
- **False negative rate:** tỷ lệ cặp cùng thực thể bị bỏ sót.
- **Review rate:** tỷ lệ cặp được chuyển sang người kiểm tra.
- **Unmerge rate:** tỷ lệ các quyết định hợp nhất phải đảo ngược do sai.

Công thức precision và recall:

```text
Precision = True Positives / (True Positives + False Positives)

Recall = True Positives / (True Positives + False Negatives)
```

Ví dụ, hệ thống đề xuất 100 cặp là trùng, trong đó 95 cặp được xác nhận đúng. Precision là 95%. Nếu tổng cộng có 120 cặp trùng thực tế trong tập kiểm tra, recall là 95/120, xấp xỉ 79,2%.

Precision cao giúp hạn chế gộp nhầm; recall cao giúp phát hiện được nhiều bản ghi trùng. Ngưỡng phù hợp tùy mức độ rủi ro của nghiệp vụ. Với hồ sơ nhạy cảm hoặc giao dịch tài chính, nên ưu tiên độ tin cậy và duyệt thủ công đối với trường hợp mơ hồ.

## 11. Những lỗi thường gặp

- Coi hai bản ghi có cùng tên là cùng một người hoặc cùng một sản phẩm.
- Coi hai bản ghi có ID khác nhau là hai thực thể chắc chắn khác nhau ngoài đời.
- Coi mọi thuộc tính khác nhau đều chứng minh hai thực thể khác nhau, dù thuộc tính có thể thay đổi.
- Dùng một trường không duy nhất như địa chỉ, ngày sinh hoặc tên làm khóa nhận diện.
- Gộp hồ sơ chỉ dựa vào điểm fuzzy matching mà không xem bằng chứng mâu thuẫn.
- Không phân biệt ID nội bộ, ID nghiệp vụ và ID của hệ thống nguồn.
- Chuẩn hóa dữ liệu quá mức, làm mất thông tin gốc hoặc tạo ra các giá trị khác nhau bị coi là giống nhau.
- Hợp nhất bản ghi nhưng không cập nhật các khóa ngoại và hệ thống phụ thuộc.
- Xóa bản ghi cũ mà không lưu ánh xạ, nguồn gốc hoặc lịch sử.
- Chỉ kiểm tra trùng trong ứng dụng mà không bảo vệ các quy tắc duy nhất bằng constraint.
- Dùng idempotency key như thể nó giải quyết mọi trường hợp hai yêu cầu khác nhau cùng tạo một thực thể.
- Đánh giá chất lượng bằng số lượng hồ sơ đã gộp thay vì precision, recall và hậu quả của quyết định sai.

## 12. Checklist phân biệt và xử lý bản ghi trùng

Trước khi kết luận hai bản ghi có cùng thực thể, hãy xác nhận:

- [ ] Đã xác định loại thực thể và ý nghĩa nghiệp vụ của từng bản ghi.
- [ ] Đã phân biệt định danh bản ghi với định danh thực thể ngoài đời.
- [ ] Đã xác định phạm vi của từng mã định danh.
- [ ] Đã phân loại thuộc tính ổn định, biến động và có thể dùng chung.
- [ ] Đã chuẩn hóa dữ liệu theo quy tắc phù hợp và vẫn giữ giá trị gốc khi cần.
- [ ] Đã kết hợp nhiều bằng chứng thay vì dựa vào một thuộc tính phổ biến.
- [ ] Đã xem xét bằng chứng mâu thuẫn và rủi ro false positive.
- [ ] Trường hợp không chắc chắn được chuyển sang quy trình xem xét.
- [ ] Đã chọn canonical ID và quy tắc hợp nhất thuộc tính.
- [ ] Các khóa ngoại và hệ thống nguồn được chuyển đổi có kiểm soát.
- [ ] Có lưu ánh xạ ID cũ, nguồn gốc, lý do và lịch sử hợp nhất.
- [ ] Các constraint và idempotency key được áp dụng đúng phạm vi nghiệp vụ.
- [ ] Chất lượng matching được đánh giá bằng precision, recall và mẫu đã xác minh.

Phân biệt bản ghi trùng với hai thực thể có thuộc tính giống nhau là bài toán về danh tính và ngữ cảnh nghiệp vụ, không chỉ là so sánh chuỗi hay tìm các hàng giống hệt nhau. Khi mô hình lưu rõ định danh, phạm vi, nguồn gốc và lịch sử quyết định, hệ thống có thể giảm dữ liệu trùng mà vẫn bảo vệ được ranh giới giữa những thực thể thực sự khác nhau.


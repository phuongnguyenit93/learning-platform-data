# Nhánh LTS, Innovation và cách xác định tính năng theo phiên bản

MySQL phát hành các phiên bản theo hai nhánh chính là **LTS (Long Term Support)** và **Innovation**. Hiểu sự khác nhau giữa hai nhánh giúp chọn phiên bản phù hợp cho môi trường phát triển và production, lập kế hoạch nâng cấp, đồng thời tránh sử dụng cú pháp hoặc hành vi mà máy chủ đang chạy chưa hỗ trợ.

Trong module **DATABASE_MYSQL**, kiến thức phiên bản là nền tảng cho các phần thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, phân quyền, sao lưu và vận hành. Một câu lệnh SQL chỉ hoạt động đúng khi phiên bản máy chủ, cấu hình và storage engine đáp ứng các điều kiện cần thiết.

## 1. Hai nhánh phát hành của MySQL

Oracle giới thiệu mô hình phát hành mới từ dòng MySQL 8.1. Mô hình này tách các bản phát hành thành hai hướng để người dùng lựa chọn giữa độ ổn định dài hạn và khả năng tiếp cận tính năng mới nhanh hơn.

| Tiêu chí | LTS | Innovation |
|---|---|---|
| Mục tiêu | Vận hành ổn định trong thời gian dài | Tiếp cận cải tiến và tính năng mới sớm |
| Nhịp phát hành | Thưa hơn; các mốc LTS cách nhau theo chu kỳ dài | Thường xuyên hơn, theo nhịp khoảng ba tháng |
| Nội dung cập nhật | Tập trung vào sửa lỗi, bảo mật và độ ổn định của dòng phát hành | Có thể bổ sung tính năng và thay đổi mới bên cạnh sửa lỗi |
| Yêu cầu nâng cấp | Có kế hoạch nâng cấp theo các mốc LTS và chính sách hỗ trợ | Cần theo dõi bản phát hành mới và nâng cấp thường xuyên hơn |
| Phù hợp với | Hệ thống production ưu tiên ổn định, đội ngũ cần chu kỳ thay đổi dễ dự đoán | Đội ngũ cần tính năng mới và có năng lực kiểm thử, triển khai nâng cấp liên tục |

**LTS** là lựa chọn phù hợp khi hệ thống cần một nền tảng ổn định trong thời gian dài. Dòng LTS vẫn nhận các bản cập nhật cần thiết theo chính sách hỗ trợ của Oracle; nhãn LTS không có nghĩa là có thể bỏ qua bản vá bảo mật hoặc không cần nâng cấp.

**Innovation** là các bản phát hành chính thức dành cho người muốn sử dụng cải tiến mới sớm. Innovation không đồng nghĩa với bản alpha, beta hay bản thử nghiệm. Tuy nhiên, vòng đời của từng dòng ngắn hơn, vì vậy tổ chức sử dụng nhánh này cần có quy trình kiểm thử và nâng cấp đều đặn.

Ví dụ về mô hình mới: MySQL 8.1, 8.2 và 8.3 là các dòng Innovation; MySQL 8.4 là mốc LTS đầu tiên của mô hình này. Không nên suy ra nhánh phát hành chỉ bằng cách nhìn một chữ số phiên bản hoặc cho rằng mọi dòng MySQL cũ đều mang nhãn LTS theo cách gọi mới. Hãy kiểm tra thông báo phát hành và chính sách hỗ trợ của đúng dòng đang triển khai.

## 2. Đọc số phiên bản MySQL

Phiên bản máy chủ thường có dạng **X.Y.Z**, ví dụ 8.4.3:

- **X.Y** xác định dòng phát hành, chẳng hạn 8.4.
- **Z** là số bản cập nhật trong dòng đó, thường chứa các sửa lỗi và cập nhật bảo mật.
- Một thay đổi có thể xuất hiện ở một bản cập nhật cụ thể, vì vậy chỉ biết dòng 8.0 hoặc 8.4 đôi khi chưa đủ để kết luận tính năng có sẵn hay chưa.

Cách đánh số đã thay đổi qua các thế hệ MySQL. Dòng 8.0 có nhiều bản cập nhật mang dạng 8.0.N; mô hình mới có các dòng như 8.1, 8.2, 8.3 và 8.4. Vì vậy, hãy đọc số phiên bản cùng thông tin nhánh phát hành thay vì áp dụng máy móc một quy tắc so sánh cho mọi thế hệ.

Không nên so sánh phiên bản như chuỗi ký tự. Ví dụ, phép so sánh từ điển có thể xếp sai 8.10 và 8.9. Khi viết công cụ kiểm tra phiên bản, hãy tách các thành phần số hoặc sử dụng thư viện so sánh phiên bản có hiểu biết về quy tắc đánh số.

### Xác định phiên bản máy chủ đang kết nối

Chạy truy vấn sau trên chính kết nối ứng dụng hoặc môi trường cần kiểm tra:

```sql
SELECT
    VERSION() AS server_version,
    @@version_comment AS distribution,
    @@version_compile_os AS compile_os,
    @@version_compile_machine AS compile_machine;
```

- **VERSION()** trả về phiên bản của máy chủ MySQL đang xử lý kết nối.
- **@@version_comment** cung cấp thông tin mô tả bản phân phối.
- Hai biến **version_compile_*** cho biết thông tin nền tảng biên dịch của máy chủ.

Có thể xem các biến liên quan bằng lệnh:

```sql
SHOW VARIABLES LIKE 'version%';
```

Lệnh **mysql --version** chạy trong terminal cho biết phiên bản **chương trình client** trên máy đang gọi lệnh. Nó không chứng minh phiên bản máy chủ ở đầu bên kia kết nối. Khi ứng dụng dùng máy chủ từ xa, container hoặc dịch vụ cơ sở dữ liệu được quản lý, hãy kiểm tra bằng truy vấn SQL trên kết nối thực tế.

## 3. Điều gì quyết định một tính năng có dùng được hay không?

Không thể kết luận chỉ từ tên MySQL hoặc số phiên bản lớn. Trước khi sử dụng một tính năng, cần kiểm tra các yếu tố sau:

1. **Phiên bản giới thiệu tính năng:** tài liệu ghi tính năng xuất hiện lần đầu ở bản nào. Nếu máy chủ thấp hơn mốc đó, cú pháp hoặc hành vi có thể chưa được hỗ trợ.
2. **Thay đổi và loại bỏ:** tính năng có thể được đánh dấu deprecated, thay đổi mặc định hoặc bị loại bỏ ở một dòng mới. Kiểm tra cả hướng dẫn nâng cấp và release notes.
3. **Bản phân phối và edition:** MySQL Community, các gói thương mại và dịch vụ tương thích MySQL có thể cung cấp tập tính năng, plugin hoặc giới hạn khác nhau. Không mặc định mọi dịch vụ mang tên MySQL đều giống hệt MySQL Server do Oracle phát hành.
4. **Storage engine:** một tính năng hoặc tùy chọn có thể chỉ áp dụng cho InnoDB, NDB hoặc một engine cụ thể. Kiểm tra engine thực tế của bảng.
5. **Cấu hình và quyền:** plugin, biến cấu hình, chế độ SQL và quyền của tài khoản có thể ảnh hưởng đến việc sử dụng tính năng.
6. **Nền tảng triển khai:** nhà cung cấp dịch vụ managed database có thể bật, tắt hoặc triển khai tính năng theo lịch riêng; hệ điều hành và kiến trúc cũng có thể tạo ra giới hạn.

Cần phân biệt ba câu hỏi:

- Máy chủ có nhận biết cú pháp không?
- Máy chủ có thực thi đúng hành vi mong đợi không?
- Tính năng có được hỗ trợ trong tổ hợp phiên bản, edition, engine và cấu hình đang dùng không?

Một câu lệnh được parser chấp nhận chưa chắc đã được thực thi như mong đợi. Đây là lý do cần đọc tài liệu đúng phiên bản và kiểm thử trên máy chủ tương ứng.

## 4. Ví dụ về khác biệt tính năng theo phiên bản

### 4.1. Ràng buộc CHECK

MySQL bắt đầu thực thi các ràng buộc **CHECK** từ phiên bản 8.0.16. Ở các phiên bản trước đó, máy chủ có thể chấp nhận cú pháp nhưng bỏ qua ràng buộc. Vì vậy, việc tạo bảng thành công trên một máy chủ cũ không chứng minh dữ liệu được kiểm tra theo điều kiện mong muốn.

Ví dụ:

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    total_amount DECIMAL(12, 2) NOT NULL,
    CONSTRAINT chk_orders_total
        CHECK (total_amount >= 0)
) ENGINE = InnoDB;
```

Trên phiên bản có thực thi **CHECK**, thao tác ghi dữ liệu có **total_amount** âm sẽ bị từ chối bởi ràng buộc. Nếu triển khai cùng schema trên phiên bản cũ hơn 8.0.16, không được dựa vào ràng buộc này để bảo vệ dữ liệu. Cần kiểm tra phiên bản đích hoặc bổ sung biện pháp xác thực phù hợp trước khi nâng cấp ứng dụng.

### 4.2. EXPLAIN ANALYZE

**EXPLAIN ANALYZE** được giới thiệu trong MySQL 8.0.18. Lệnh này thực thi câu truy vấn và cung cấp thông tin thực tế như thời gian, số hàng quan sát được ở các iterator và số vòng lặp. Nó hữu ích khi học cách đọc kế hoạch thực thi và tối ưu truy vấn.

```sql
EXPLAIN ANALYZE
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id;
```

Khác với việc chỉ xem kế hoạch ước lượng, **EXPLAIN ANALYZE** chạy câu lệnh được phân tích. Hãy dùng với truy vấn có thể thực thi an toàn, chú ý chi phí tài nguyên và tránh chạy tùy tiện trên câu lệnh ghi dữ liệu hoặc truy vấn có hàm gây tác động phụ. Nếu máy chủ thấp hơn 8.0.18, hãy dùng hình thức **EXPLAIN** được phiên bản đó hỗ trợ và đọc tài liệu tương ứng.

Hai ví dụ trên cho thấy phải kiểm tra cả phiên bản cụ thể lẫn ngữ nghĩa của tính năng. Một bản vá trong cùng dòng 8.0 cũng có thể tạo ra khác biệt đáng kể.

## 5. Quy trình xác minh một tính năng trước khi dùng

Khi muốn áp dụng một cú pháp SQL, loại index, tùy chọn transaction hoặc công cụ quản trị mới, hãy làm theo quy trình sau:

1. **Xác định máy chủ đích.** Kết nối vào đúng môi trường và lấy **VERSION()** cùng thông tin phân phối. Nếu có nhiều cụm hoặc nhiều môi trường, kiểm tra từng cụm.
2. **Tìm tài liệu đúng phiên bản.** Mở MySQL Reference Manual của dòng máy chủ đang chạy. Đọc mục mô tả tính năng và ghi nhận phiên bản giới thiệu.
3. **Đọc release notes.** Tìm thay đổi trong bản giới thiệu tính năng, các bản vá tiếp theo và hướng dẫn nâng cấp. Kiểm tra trạng thái deprecated hoặc removed nếu có.
4. **Kiểm tra điều kiện áp dụng.** Xác nhận edition, storage engine, plugin, biến cấu hình, SQL mode và quyền cần thiết.
5. **Thử nghiệm trên môi trường tương đương.** Dùng cùng phiên bản, cấu hình và engine với production. Kiểm tra cả dữ liệu hợp lệ, dữ liệu biên và trường hợp bị từ chối.
6. **Đánh giá tương thích ngược.** Nếu ứng dụng hỗ trợ nhiều phiên bản, xác định phiên bản thấp nhất được hỗ trợ và thiết kế migration sao cho không làm hỏng môi trường chưa nâng cấp.
7. **Ghi lại quyết định.** Lưu phiên bản tối thiểu, điều kiện sử dụng và cách kiểm thử vào tài liệu triển khai hoặc migration.

Có thể lập bảng tương thích để cả nhóm cùng kiểm tra:

| Môi trường | Phiên bản máy chủ | Nhánh | Tính năng bắt buộc | Kết quả kiểm thử |
|---|---|---|---|---|
| Development | Ghi phiên bản thực tế | LTS/Innovation | Liệt kê tính năng | Đạt/Không đạt |
| Staging | Ghi phiên bản thực tế | LTS/Innovation | Liệt kê tính năng | Đạt/Không đạt |
| Production | Ghi phiên bản thực tế | LTS/Innovation | Liệt kê tính năng | Đạt/Không đạt |

Không điền phiên bản giả định vào bảng. Hãy lấy dữ liệu từ từng môi trường để phát hiện tình trạng development đã dùng tính năng mới nhưng staging hoặc production chưa hỗ trợ.

## 6. Chọn nhánh nào cho hệ thống?

Chọn **LTS** khi hệ thống ưu tiên thời gian vận hành ổn định, phụ thuộc nhiều vào ứng dụng hoặc plugin, có cửa sổ bảo trì hạn chế, hoặc đội ngũ muốn lập kế hoạch nâng cấp theo các mốc dài hơn. Đây thường là điểm khởi đầu hợp lý cho hệ thống production cần giảm tần suất thay đổi.

Chọn **Innovation** khi hệ thống cần thử nghiệm hoặc triển khai sớm các tính năng mới, đội ngũ có pipeline kiểm thử tự động, có môi trường staging tương đương production và đủ khả năng theo dõi, triển khai các bản nâng cấp thường xuyên.

Trước khi quyết định, hãy trả lời:

- Tính năng mới có giải quyết một nhu cầu cụ thể không?
- Ứng dụng, connector, driver, plugin và công cụ backup có hỗ trợ phiên bản dự kiến không?
- Có thể kiểm thử migration, hiệu năng, transaction và khôi phục backup trước khi nâng cấp không?
- Đội ngũ có lịch bảo trì và người chịu trách nhiệm theo dõi release notes không?
- Chính sách hỗ trợ của Oracle hoặc nhà cung cấp dịch vụ có đáp ứng thời gian vận hành dự kiến không?

Không chọn Innovation chỉ vì số phiên bản cao hơn. Cũng không xem LTS là lý do để trì hoãn mọi bản cập nhật. Quyết định cần dựa trên tính năng thực sự cần, khả năng tương thích, năng lực vận hành và chính sách hỗ trợ hiện hành.

## 7. Lập kế hoạch nâng cấp và triển khai

Phiên bản MySQL phải được quản lý như một phần của cấu hình ứng dụng:

- **Ghim phiên bản triển khai:** với container hoặc hạ tầng tự động, dùng tag phiên bản cụ thể hoặc image digest đã kiểm soát. Tránh để môi trường production tự thay đổi phiên bản ngoài kế hoạch.
- **Đồng bộ các môi trường:** development, CI, staging và production nên dùng cùng dòng phiên bản, hoặc có ma trận tương thích được ghi rõ.
- **Đọc hướng dẫn nâng cấp:** kiểm tra đường nâng cấp được hỗ trợ, thay đổi mặc định, tính năng bị loại bỏ và yêu cầu chuyển đổi dữ liệu.
- **Sao lưu và thử khôi phục:** xác minh backup có thể phục hồi trước khi thay đổi máy chủ. Một file backup được tạo thành công chưa đủ; cần thử restore.
- **Đo lại hiệu năng:** sau nâng cấp, kiểm tra truy vấn quan trọng, index, execution plan, transaction và tải đồng thời. Kết quả có thể thay đổi do optimizer, thống kê hoặc mặc định cấu hình.
- **Có phương án quay lui:** xác định trước cách khôi phục dịch vụ và dữ liệu nếu kiểm thử sau nâng cấp không đạt. Không giả định có thể hạ phiên bản bằng cách thay image rồi khởi động lại trên thư mục dữ liệu đã được phiên bản mới thay đổi.

Một lần nâng cấp thành công cần chứng minh cả ứng dụng kết nối được, migration chạy đúng, dữ liệu còn nguyên vẹn, truy vấn trọng yếu đáp ứng yêu cầu và quy trình backup/restore vẫn hoạt động.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| **mysql --version** cho biết phiên bản server | Lệnh này cho biết phiên bản client; dùng **SELECT VERSION()** trên kết nối server |
| Innovation là bản thử nghiệm | Đây là nhánh phát hành chính thức; điểm khác biệt chính là nhịp tính năng và yêu cầu nâng cấp |
| LTS không cần cập nhật | LTS vẫn cần các bản vá và cập nhật theo chính sách hỗ trợ |
| Cùng tên MySQL nghĩa là cùng tính năng | Cần kiểm tra bản phân phối, edition, engine, cấu hình và nhà cung cấp |
| Cú pháp chạy được nghĩa là hành vi đúng | Phải xác minh ngữ nghĩa và kiểm thử trên phiên bản đích |
| Máy phát triển mới hơn production là vô hại | Migration hoặc truy vấn có thể dùng tính năng mà production chưa hỗ trợ |
| Nâng cấp chỉ là đổi số phiên bản | Cần kiểm thử tương thích, dữ liệu, hiệu năng, backup và khôi phục |

## 9. Ghi nhớ

- LTS ưu tiên ổn định và chu kỳ hỗ trợ dài; Innovation đưa cải tiến mới đến người dùng thường xuyên hơn.
- MySQL 8.4 là mốc LTS đầu tiên trong mô hình phát hành mới; 8.1, 8.2 và 8.3 là các dòng Innovation.
- Luôn lấy phiên bản từ máy chủ đang kết nối bằng **SELECT VERSION()**.
- Tra cứu tài liệu và release notes đúng dòng phiên bản; kiểm tra cả mốc giới thiệu, thay đổi và loại bỏ tính năng.
- Phiên bản chỉ là một điều kiện. Edition, storage engine, cấu hình, quyền và nền tảng triển khai cũng có thể quyết định tính năng hoạt động.
- Chọn nhánh phát hành dựa trên nhu cầu tính năng và năng lực vận hành; kiểm thử nâng cấp, hiệu năng và khôi phục trước khi đưa vào production.

Khi đã xác định đúng phiên bản và nhánh phát hành, việc học thiết kế schema, chọn kiểu dữ liệu, tạo index, quản lý transaction và đọc execution plan sẽ bám sát khả năng thực tế của máy chủ MySQL mà hệ thống đang sử dụng.


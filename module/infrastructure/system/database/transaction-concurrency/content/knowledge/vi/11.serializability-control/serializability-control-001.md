# Phát hiện xung đột thay vì chặn trước mọi truy cập

Khi nhiều giao dịch cùng truy cập dữ liệu, hệ quản trị cơ sở dữ liệu (DBMS) cần bảo đảm kết quả cuối cùng tương đương với một thứ tự thực thi tuần tự hợp lệ. Một cách phổ biến là khóa tài nguyên trước khi cho phép thao tác có nguy cơ xung đột. Giao dịch phải chờ nếu một giao dịch khác đang giữ khóa không tương thích.

Tuy nhiên, không phải mọi cặp giao dịch đều thực sự xung đột. Nếu phần lớn giao dịch chỉ đọc hoặc cập nhật những dữ liệu khác nhau, việc chặn trước mọi truy cập có thể làm giảm tính đồng thời dù nhiều thao tác có thể chạy song song an toàn. Một hướng tiếp cận khác là cho phép giao dịch thực hiện trên dữ liệu mà chúng đã đọc, sau đó **kiểm tra xung đột trước khi chấp nhận kết quả**. Nếu kết quả không thể được sắp xếp thành một lịch tuần tự hợp lệ, DBMS hủy một giao dịch và yêu cầu thực hiện lại.

Ý tưởng này thường được gọi là **kiểm soát đồng thời lạc quan (Optimistic Concurrency Control — OCC)** hoặc kiểm soát dựa trên xác thực (validation-based concurrency control). Nó phù hợp khi xung đột hiếm, nhưng có thể tốn kém nếu nhiều giao dịch cùng sửa một vùng dữ liệu nóng.

## 1. Từ chặn trước đến phát hiện khi xác thực

Hai cách tiếp cận khác nhau ở thời điểm xử lý nguy cơ xung đột:

- **Kiểm soát bi quan (pessimistic concurrency control):** giả định xung đột có thể xảy ra. Giao dịch lấy khóa trước khi đọc hoặc ghi tài nguyên cần bảo vệ; nếu khóa không tương thích đã được giữ, giao dịch phải chờ.
- **Kiểm soát lạc quan (optimistic concurrency control):** giả định phần lớn giao dịch có thể hoàn tất mà không xung đột. Giao dịch đọc và tính toán trước, sau đó xác thực các phụ thuộc trước khi công bố thay đổi.

Ví dụ, hai người dùng mở cùng một hồ sơ khách hàng. Người dùng A đổi số điện thoại, người dùng B đổi địa chỉ. Nếu hệ thống khóa toàn bộ hồ sơ ngay khi mỗi người mở màn hình và giữ khóa trong suốt thời gian người dùng suy nghĩ, người còn lại có thể phải chờ rất lâu. Với cách lạc quan, cả hai có thể chỉnh sửa trên phiên bản đã đọc. Khi lưu, hệ thống kiểm tra xem phiên bản đó còn mới hay đã bị thay đổi. Nếu dữ liệu không xung đột, thay đổi có thể được chấp nhận; nếu có xung đột, hệ thống yêu cầu tải lại hoặc giải quyết thay đổi.

OCC không có nghĩa là bỏ qua tính nhất quán. Giao dịch chỉ được chấp nhận sau khi DBMS hoặc ứng dụng chứng minh rằng kết quả của nó vẫn tuân thủ quy tắc đồng thời đã chọn.

## 2. Xung đột là gì?

Hai thao tác có khả năng xung đột khi chúng truy cập cùng một dữ liệu và ít nhất một thao tác ghi dữ liệu đó. Với một mục dữ liệu `X`, ba dạng xung đột cơ bản là:

| Thao tác thứ nhất | Thao tác thứ hai | Có xung đột dữ liệu? | Giải thích |
|---|---|---|---|
| Đọc `X` | Đọc `X` | Không | Cả hai chỉ quan sát cùng một giá trị. |
| Đọc `X` | Ghi `X` | Có | Giá trị được đọc có thể trở nên cũ sau khi giao dịch kia ghi. |
| Ghi `X` | Đọc `X` | Có | Kết quả đọc phụ thuộc vào thứ tự trước hoặc sau lần ghi. |
| Ghi `X` | Ghi `X` | Có | Hai thay đổi có thể ghi đè hoặc phụ thuộc vào thứ tự thực hiện. |

Một giao dịch thường được mô tả bằng hai tập tài nguyên:

- **Read set (tập đọc):** các hàng, khóa chỉ mục, khoảng giá trị hoặc dữ liệu mà giao dịch đã đọc và dựa vào đó để tính toán.
- **Write set (tập ghi):** các tài nguyên mà giao dịch dự định thay đổi.

Nếu tập ghi của giao dịch này giao với tập đọc hoặc tập ghi của giao dịch khác, có thể tồn tại phụ thuộc cần xác thực. Việc chỉ so sánh các hàng được cập nhật là chưa đủ trong những giao dịch có điều kiện hoặc ràng buộc liên quan đến nhiều hàng.

### Xung đột và khả tuần tự

Mục tiêu của kiểm soát khả tuần tự (serializability) là bảo đảm kết quả đồng thời tương đương với một thứ tự chạy từng giao dịch một. Để phân tích, có thể lập đồ thị phụ thuộc:

- Mỗi giao dịch là một đỉnh.
- Một cạnh từ giao dịch A đến B biểu diễn rằng thao tác của A phải đứng trước thao tác xung đột của B trong thứ tự tương đương.
- Nếu đồ thị phụ thuộc có chu trình, lịch thực thi không conflict-serializable theo các phụ thuộc được biểu diễn.

OCC dùng thông tin đọc/ghi và quy tắc xác thực để phát hiện khi một giao dịch không còn có thể được đặt vào thứ tự tuần tự hợp lệ. Thuật toán cụ thể có thể khác nhau giữa các DBMS; không phải mọi hệ thống đều lưu hai tập đọc/ghi theo cùng một cách.

## 3. Ba giai đoạn của kiểm soát lạc quan

Mô hình OCC kinh điển chia giao dịch thành ba giai đoạn: đọc, xác thực và ghi.

```text
             Bắt đầu giao dịch
                     |
                     v
          +---------------------+
          | 1. Giai đoạn đọc    |
          | Đọc và tính toán    |
          | thay đổi tạm thời   |
          +---------------------+
                     |
                     v
          +---------------------+
          | 2. Giai đoạn        |
          | xác thực            |
          | Kiểm tra các phụ    |
          | thuộc/xung đột      |
          +---------------------+
               /         \
          Hợp lệ         Xung đột
             |              |
             v              v
    +----------------+  +----------------+
    | 3. Giai đoạn   |  | Hủy giao dịch  |
    | ghi và commit  |  | rồi thử lại    |
    +----------------+  +----------------+
```

### 3.1. Giai đoạn đọc (read phase)

Giao dịch đọc dữ liệu cần thiết và thực hiện tính toán. Trong mô hình OCC, các thay đổi được giữ trong vùng làm việc riêng hoặc được ghi nhận như các thay đổi chưa công bố. Giao dịch khác có thể tiếp tục thực hiện công việc của mình mà không phải chờ khóa độc quyền trên mọi mục dữ liệu mà giao dịch hiện tại đọc.

Ví dụ, giao dịch A đọc số lượng hàng tồn kho và tính số lượng cần trừ. Trong lúc A tính toán, giao dịch B cũng có thể đọc cùng dữ liệu. Chưa giao dịch nào được phép giả định rằng thay đổi của mình đã được commit.

Tùy DBMS, giai đoạn đọc có thể dựa trên snapshot, phiên bản dữ liệu hoặc cơ chế lưu trữ riêng. OCC là mô hình kiểm soát đồng thời; nó không quy định mọi DBMS phải dùng cùng một kỹ thuật lưu phiên bản.

### 3.2. Giai đoạn xác thực (validation phase)

Trước khi commit, giao dịch kiểm tra xem dữ liệu mà nó đã đọc còn phù hợp với những thay đổi đã được giao dịch khác commit hay không. Nó cũng cần kiểm tra các ghi dự kiến có gây ra phụ thuộc không thể sắp xếp thành thứ tự tuần tự hợp lệ hay không.

Nếu xác thực thành công, giao dịch có thể được đặt vào một vị trí phù hợp trong thứ tự tuần tự tương đương và tiếp tục ghi. Nếu xác thực thất bại, giao dịch bị hủy (abort) vì kết quả tính toán của nó dựa trên trạng thái không còn phù hợp hoặc tạo ra phụ thuộc không an toàn.

Điểm quan trọng là xác thực phải xét đủ phạm vi dữ liệu mà giao dịch phụ thuộc. Với thao tác đọc một hàng, kiểm tra phiên bản hàng có thể đủ để phát hiện cập nhật đồng thời trên hàng đó. Với truy vấn như “đếm số đơn hàng đang mở trong tháng”, giao dịch phụ thuộc vào cả một tập hàng thỏa điều kiện. Nếu chỉ kiểm tra các hàng đã tồn tại mà không xét hàng mới được chèn, hệ thống có thể bỏ sót xung đột dạng phantom.

### 3.3. Giai đoạn ghi (write phase)

Sau khi xác thực thành công, DBMS công bố các thay đổi và hoàn tất commit. Việc ghi cần được thực hiện theo cách bảo đảm các giao dịch khác không quan sát một trạng thái commit dở dang. DBMS vẫn có thể dùng khóa ngắn hạn, latch hoặc cơ chế đồng bộ nội bộ để bảo vệ thao tác vật lý và điểm commit.

Vì vậy, “không chặn trước mọi truy cập” không có nghĩa hệ thống không bao giờ dùng khóa. Ý tưởng là trì hoãn việc quyết định xung đột đến giai đoạn phù hợp và tránh giữ khóa chặn dài hạn cho những thao tác có thể chạy đồng thời.

## 4. Ví dụ: hai người cùng cập nhật một sản phẩm

Giả sử bảng `Product` lưu số lượng hàng và một số phiên bản:

| product_id | stock | version |
|---:|---:|---:|
| 10 | 5 | 7 |

Hai giao dịch A và B cùng đọc `stock = 5`, `version = 7`. A muốn trừ một sản phẩm; B cũng muốn trừ một sản phẩm. Nếu cả hai chỉ ghi giá trị mới là `4` mà không kiểm tra phiên bản, giao dịch ghi sau có thể ghi đè kết quả của giao dịch trước. Một lượt bán bị mất khỏi số liệu tồn kho.

Một cách kiểm soát lạc quan ở cấp hàng là dùng cột phiên bản (version column):

```sql
-- Cả hai giao dịch đều đã đọc version = 7.
-- Giao dịch A thử cập nhật:
UPDATE Product
SET stock = stock - 1,
    version = version + 1
WHERE product_id = 10
  AND version = 7
  AND stock > 0;
```

Nếu A cập nhật trước, hàng chuyển thành `stock = 4`, `version = 8`; số hàng bị ảnh hưởng là 1. Khi B chạy cùng điều kiện với `version = 7`, điều kiện không còn đúng nên số hàng bị ảnh hưởng là 0. B phát hiện phiên bản đã thay đổi và không được tiếp tục với kết quả tính toán cũ.

Ứng dụng có thể đọc lại dữ liệu rồi thử lại toàn bộ nghiệp vụ nếu vẫn còn hàng, hoặc thông báo cho người dùng rằng trạng thái đã thay đổi. Nếu số lượng đã bằng 0, nghiệp vụ bán hàng phải từ chối. Cần phân biệt xung đột phiên bản với việc hết hàng bằng cách đọc lại trạng thái hoặc dùng một kết quả nghiệp vụ phù hợp.

Mẫu câu lệnh này là cách cập nhật có điều kiện thường dùng với SQL. Cú pháp tham số thực tế phụ thuộc thư viện truy cập dữ liệu. Ứng dụng phải kiểm tra số hàng bị ảnh hưởng trong cùng giao dịch và coi kết quả bằng 0 là dấu hiệu không thể áp dụng thay đổi theo phiên bản đã đọc.

### Vì sao cần cập nhật nguyên tử?

Điều kiện phiên bản và phép cập nhật phải được DBMS đánh giá như một thao tác nguyên tử. Nếu ứng dụng tách thành hai bước “đọc version”, rồi “ghi mà không kèm điều kiện version”, một giao dịch khác vẫn có thể thay đổi dữ liệu ở giữa hai bước. Đó chính là khoảng thời gian tạo ra lost update.

Một biến thể có thể dùng giá trị cũ trong mệnh đề `WHERE` và giá trị mới trong `SET`:

```sql
UPDATE Customer
SET phone = :newPhone,
    version = version + 1
WHERE customer_id = :customerId
  AND version = :expectedVersion;
```

Nếu số hàng bị ảnh hưởng bằng 1, cập nhật theo phiên bản đã đọc thành công. Nếu bằng 0, bản ghi không còn ở phiên bản dự kiến hoặc không tồn tại; ứng dụng cần phân biệt hai trường hợp theo yêu cầu nghiệp vụ.

## 5. Kiểm tra phiên bản có phải là kiểm soát khả tuần tự đầy đủ?

Không phải lúc nào cũng vậy. So sánh version ở cấp hàng rất hữu ích để phát hiện hai người cùng sửa một hàng, nhưng không tự động bảo vệ mọi quy tắc nghiệp vụ liên quan đến nhiều hàng hoặc điều kiện truy vấn.

Xét quy tắc: “Luôn phải có ít nhất một bác sĩ trực”. Bảng `DoctorDuty` ban đầu có hai hàng:

| doctor_id | on_call |
|---:|---|
| 1 | TRUE |
| 2 | TRUE |

Hai giao dịch có thể xảy ra đồng thời:

1. Giao dịch A đọc cả hai hàng và thấy có hai bác sĩ trực; A đổi bác sĩ 1 thành `FALSE`.
2. Giao dịch B cũng đọc cả hai hàng và thấy có hai bác sĩ trực; B đổi bác sĩ 2 thành `FALSE`.
3. A và B cập nhật hai hàng khác nhau, nên kiểm tra version riêng từng hàng đều có thể thành công.
4. Cả hai commit, khiến không còn bác sĩ nào trực.

Đây là dạng **write skew**. Hai giao dịch không ghi cùng một hàng, nhưng mỗi giao dịch đọc dữ liệu mà giao dịch kia thay đổi. Việc chỉ so sánh phiên bản trên hàng được ghi không phát hiện đầy đủ phụ thuộc này.

Để bảo vệ quy tắc nhiều hàng, hệ thống cần một cơ chế hiểu được phạm vi đọc và quan hệ phụ thuộc, chẳng hạn:

- Dùng mức cô lập `SERIALIZABLE` nếu DBMS triển khai cơ chế bảo đảm khả tuần tự phù hợp.
- Dùng cơ chế phát hiện phụ thuộc đọc-ghi hoặc predicate/range để xác thực cả điều kiện truy vấn.
- Thiết kế một hàng tổng hợp/guard row đại diện cho tài nguyên nghiệp vụ và cập nhật nó có điều kiện để các giao dịch tranh chấp trên cùng điểm kiểm soát.
- Dùng ràng buộc dữ liệu hoặc mô hình dữ liệu khác nếu quy tắc có thể được biểu diễn và bảo vệ trực tiếp bằng DBMS.

Chọn giải pháp nào phụ thuộc DBMS, mức tải và cách biểu diễn quy tắc nghiệp vụ. Không nên coi một cột `version` trên từng hàng là bằng chứng rằng toàn bộ giao dịch đã được kiểm soát khả tuần tự.

## 6. Vai trò của MVCC và Serializable Snapshot Isolation

Kiểm soát lạc quan thường được nhắc cùng với **MVCC (Multi-Version Concurrency Control)**, nhưng hai khái niệm không đồng nghĩa:

- MVCC là kỹ thuật duy trì nhiều phiên bản dữ liệu để giao dịch có thể đọc một phiên bản phù hợp với snapshot của mình.
- OCC là cách kiểm soát đồng thời dựa trên giả định xung đột ít xảy ra và xác thực trước khi chấp nhận kết quả.
- Một DBMS có thể kết hợp MVCC với kiểm tra xung đột lạc quan, nhưng việc dùng MVCC tự nó không bảo đảm mọi lịch giao dịch đều khả tuần tự.

Ví dụ, mức cô lập Snapshot Isolation cho phép giao dịch đọc một snapshot nhất quán và thường ngăn hai giao dịch cùng ghi đè một hàng theo cách trực tiếp. Tuy nhiên, các giao dịch cập nhật những hàng khác nhau vẫn có thể tạo ra write skew như ví dụ bác sĩ trực. Vì vậy, snapshot nhất quán không tự động đồng nghĩa với serializable.

Một hướng triển khai là **Serializable Snapshot Isolation (SSI)**. Thay vì khóa chặn mọi lần đọc, cơ chế SSI theo dõi các phụ thuộc đọc-ghi có thể dẫn đến lịch không tuần tự hóa được. Nếu phát hiện cấu trúc phụ thuộc nguy hiểm, hệ thống có thể hủy một giao dịch để giữ bảo đảm `SERIALIZABLE`.

PostgreSQL là một ví dụ về DBMS dùng SSI cho mức cô lập `SERIALIZABLE`. Predicate lock trong cơ chế này ghi nhận phạm vi dữ liệu được đọc để phát hiện xung đột tiềm ẩn; chúng phục vụ theo dõi phụ thuộc và không hoạt động như khóa chặn thông thường. Khi phát hiện nguy cơ vi phạm khả tuần tự, PostgreSQL có thể trả về lỗi serialization failure để ứng dụng thực hiện lại giao dịch. Các DBMS khác có thể dùng thuật toán và cách hiển thị lỗi khác.

Do đó, khi chọn mức cô lập hoặc đọc tài liệu DBMS, cần xác định rõ hệ thống đang dùng:

- Khóa bi quan và thời gian giữ khóa nào?
- Snapshot/MVCC cung cấp dữ liệu đọc theo phiên bản nào?
- Xung đột đọc-ghi và truy vấn theo điều kiện được phát hiện ra sao?
- Giao dịch có thể bị hủy ở thời điểm nào và ứng dụng nhận biết bằng lỗi gì?

## 7. So sánh các cách tiếp cận

| Tiêu chí | Khóa bi quan | OCC / xác thực lạc quan | MVCC kết hợp SSI |
|---|---|---|---|
| Thời điểm xử lý xung đột | Trước hoặc trong khi truy cập tài nguyên | Trước khi chấp nhận thay đổi/commit | Theo dõi phụ thuộc và phát hiện nguy cơ trong quá trình giao dịch |
| Khi có xung đột | Giao dịch thường phải chờ khóa được giải phóng | Một giao dịch có thể bị hủy và phải chạy lại | Một giao dịch có thể bị hủy với lỗi serialization |
| Đọc đồng thời | Có thể bị khóa ghi chặn tùy chế độ và DBMS | Có thể đọc mà không chờ khóa ghi dài hạn | Snapshot giúp đọc phiên bản; SSI theo dõi phụ thuộc đọc-ghi |
| Chi phí nổi bật | Chờ khóa, quản lý khóa, deadlock | Công việc bị lãng phí khi phải abort/retry | Lưu phiên bản, theo dõi phụ thuộc và retry |
| Phù hợp | Xung đột thường xuyên hoặc cần giữ quyền truy cập trước khi sửa | Xung đột hiếm, giao dịch ngắn, nhiều đọc | Cần snapshot và bảo đảm serializable với mức chặn đọc thấp |

Đây là so sánh theo mô hình khái niệm. DBMS thực tế thường kết hợp nhiều cơ chế: dùng khóa cho ghi, MVCC cho đọc, kiểm tra phiên bản ở tầng ứng dụng và phát hiện phụ thuộc ở mức cô lập cao.

## 8. Khi nào nên dùng kiểm soát lạc quan?

OCC thường phù hợp khi:

- Xung đột ghi trên cùng tài nguyên xảy ra ít.
- Phần lớn thao tác là đọc hoặc tính toán trên các dữ liệu ít chồng lấn.
- Giao dịch ngắn, có thể xác thực nhanh và chạy lại với chi phí thấp.
- Hệ thống có cách phát hiện phiên bản cũ hoặc phụ thuộc xung đột đáng tin cậy.
- Nghiệp vụ có thể xử lý trường hợp lưu thất bại do dữ liệu đã thay đổi.

Ví dụ phù hợp có thể là chỉnh sửa hồ sơ ít khi đồng thời, cập nhật cấu hình, lưu bản nháp, hoặc xử lý các bản ghi độc lập. Cơ chế version/ETag trong API cũng là một dạng kiểm tra cập nhật có điều kiện: máy khách gửi phiên bản đã đọc, máy chủ chỉ chấp nhận ghi nếu phiên bản hiện tại vẫn khớp.

OCC thường kém phù hợp khi:

- Nhiều giao dịch liên tục cập nhật cùng một hàng hoặc cùng một nhóm tài nguyên nóng.
- Giao dịch kéo dài, đọc nhiều dữ liệu rồi mới xác thực.
- Chi phí tính toán trước commit lớn, khiến mỗi lần abort lãng phí nhiều công việc.
- Tỷ lệ retry cao gây tăng tải và làm các giao dịch khác càng khó hoàn tất.
- Nghiệp vụ có thao tác bên ngoài không thể hoàn tác hoặc chạy lặp an toàn.

Trong các trường hợp này, khóa bi quan trên phạm vi cần thiết hoặc một thiết kế dữ liệu khác có thể hiệu quả hơn. Không có lý do để mặc định OCC luôn nhanh hơn khóa.

## 9. Thiết kế retry an toàn

Một giao dịch bị hủy do xung đột thường có thể chạy lại, nhưng việc retry cần được thiết kế cẩn thận.

### Chạy lại toàn bộ giao dịch

Khi validation thất bại, giao dịch phải đọc lại dữ liệu và tính toán lại từ trạng thái mới. Chỉ gửi lại câu lệnh `UPDATE` cuối cùng với các giá trị đã tính từ snapshot cũ có thể lặp lại chính lỗi ban đầu.

Quy trình khái niệm:

```text
for mỗi lần thử trong giới hạn cho phép:
    bắt đầu giao dịch mới
    đọc dữ liệu mới nhất theo mức cô lập
    kiểm tra quy tắc nghiệp vụ
    tính toán thay đổi
    ghi có điều kiện / thực hiện commit

    nếu commit thành công:
        trả về kết quả

    nếu gặp lỗi xung đột có thể retry:
        rollback nếu cần
        chờ một khoảng ngắn có giới hạn
        thử lại toàn bộ giao dịch

trả về lỗi xung đột cho tầng gọi
```

Đây là mã giả. Ứng dụng phải nhận diện đúng loại lỗi có thể retry của DBMS và driver; không được lặp lại mọi lỗi SQL một cách mù quáng.

### Giới hạn số lần thử

Retry vô hạn có thể khiến một giao dịch liên tục thất bại và tiêu thụ tài nguyên. Nên đặt giới hạn số lần thử, ghi nhận số lần xung đột và trả về lỗi có thể xử lý nếu vẫn không thành công. Với tải cạnh tranh cao, backoff tăng dần và thêm jitter ngẫu nhiên có thể giảm việc nhiều giao dịch cùng retry đúng một thời điểm.

### Không lặp lại tác động bên ngoài

Một giao dịch có thể gửi email, gọi cổng thanh toán, phát thông điệp hoặc tạo tệp. Nếu các tác động này xảy ra trước khi DB commit và giao dịch phải retry, người nhận có thể nhận email hai lần hoặc hệ thống thanh toán bị gọi lặp.

Vì vậy, phần có thể retry nên tập trung vào thao tác dữ liệu trong giao dịch. Chỉ thực hiện tác động bên ngoài sau commit hoặc dùng mẫu thiết kế như transactional outbox và khóa idempotency để bảo đảm xử lý lặp an toàn. Một lần rollback cơ sở dữ liệu không thể tự hoàn tác một yêu cầu HTTP đã gửi sang hệ thống khác.

## 10. Cách triển khai và quan sát trong ứng dụng

Khi áp dụng phát hiện xung đột, cần xác định rõ lớp nào chịu trách nhiệm kiểm tra:

1. **Tầng cơ sở dữ liệu:** chọn mức cô lập và cơ chế phát hiện phụ thuộc mà DBMS cung cấp.
2. **Tầng truy vấn:** dùng điều kiện cập nhật nguyên tử, ràng buộc và chỉ mục phù hợp để kiểm tra trạng thái ngay lúc ghi.
3. **Tầng ứng dụng:** lưu phiên bản đã đọc, gửi lại phiên bản kỳ vọng khi cập nhật, kiểm tra số hàng bị ảnh hưởng và xử lý xung đột.
4. **Tầng API/UI:** trả về phản hồi có ý nghĩa khi dữ liệu đã thay đổi, cho phép tải lại hoặc kết hợp thay đổi khi phù hợp.

Với API cập nhật tài nguyên, HTTP `ETag` kết hợp `If-Match` có thể biểu diễn điều kiện phiên bản. Nếu tài nguyên đã đổi kể từ lúc máy khách đọc, máy chủ có thể từ chối cập nhật với trạng thái phù hợp, thường là `412 Precondition Failed`. Đây là cơ chế kiểm tra điều kiện ở giao thức HTTP; nó cần được nối với một cập nhật nguyên tử ở cơ sở dữ liệu để tránh race condition giữa lúc kiểm tra và lúc ghi.

Nên theo dõi ít nhất các chỉ số sau:

- Số lần validation thất bại hoặc lỗi serialization theo loại giao dịch.
- Tỷ lệ retry trên tổng số giao dịch và số lần thử trung bình.
- Tỷ lệ giao dịch cuối cùng thất bại sau khi hết giới hạn retry.
- Độ trễ trung vị và p95/p99, bao gồm cả thời gian làm lại công việc.
- Các hàng, khóa, phân vùng hoặc điều kiện truy vấn thường xuyên xuất hiện trong xung đột.
- Mức sử dụng CPU và I/O tăng thêm do giao dịch bị hủy phải chạy lại.

Nếu một khóa nghiệp vụ nóng tạo ra nhiều xung đột, cần xem xét lại thiết kế: phân vùng dữ liệu, giảm thời gian giao dịch, gộp cập nhật, dùng hàng tổng hợp hoặc chuyển sang khóa bi quan trên đúng tài nguyên tranh chấp. Chỉ tăng số lần retry có thể che khuất vấn đề mà không giải quyết nguyên nhân.

## 11. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| OCC nghĩa là không dùng khóa ở bất kỳ đâu. | DBMS vẫn có thể dùng khóa hoặc latch ngắn hạn để bảo vệ thao tác ghi, metadata và điểm commit. |
| Hai giao dịch đọc cùng dữ liệu luôn xung đột. | Đọc-đọc thường không tạo xung đột dữ liệu; nguy cơ xuất hiện khi có ghi liên quan hoặc phụ thuộc khác. |
| Kiểm tra version trên hàng là đủ cho mọi giao dịch. | Nó phát hiện cập nhật cạnh tranh trên hàng được kiểm tra, nhưng có thể bỏ sót write skew và xung đột theo predicate. |
| Dùng MVCC là đã có serializable. | Snapshot/MVCC giúp đọc phiên bản nhất quán, nhưng mức snapshot có thể vẫn cho phép write skew. |
| Validation thất bại chỉ cần chạy lại câu UPDATE cuối. | Cần đọc lại và tính toán lại toàn bộ giao dịch từ snapshot mới. |
| Retry càng nhiều càng tốt. | Retry quá mức làm tăng tải và có thể gây starvation; cần giới hạn và quan sát tỷ lệ xung đột. |
| Rollback sẽ hoàn tác mọi tác động của giao dịch. | Rollback cơ sở dữ liệu không hoàn tác email, HTTP request hoặc thanh toán đã gửi ra bên ngoài. |

## 12. Cách lựa chọn cơ chế cho một quy tắc nghiệp vụ

Trước khi chọn OCC, hãy trả lời ba câu hỏi:

**Thứ nhất, giao dịch phụ thuộc vào dữ liệu nào?** Nếu chỉ sửa một hàng, version check có thể phát hiện cập nhật đồng thời trên hàng đó. Nếu giao dịch đọc một tập hàng theo điều kiện hoặc kiểm tra tổng số lượng, phạm vi xác thực phải bao phủ cả điều kiện và dữ liệu có thể xuất hiện sau đó.

**Thứ hai, xung đột xảy ra thường xuyên đến đâu?** Nếu hiếm, xác thực và retry có thể rẻ hơn việc giữ khóa chặn trong thời gian dài. Nếu nhiều giao dịch liên tục tranh chấp cùng tài nguyên, chặn có kiểm soát hoặc thay đổi mô hình dữ liệu có thể tiết kiệm công việc hơn.

**Thứ ba, giao dịch có thể chạy lại an toàn không?** Nếu có tác động bên ngoài, chi phí tính toán lớn hoặc nghiệp vụ không thể lặp lại, cần thiết kế idempotency, outbox hoặc một ranh giới giao dịch khác trước khi bật retry tự động.

Phát hiện xung đột là cách trì hoãn quyết định chặn cho đến khi có đủ thông tin về các thao tác thực sự xảy ra. Nó giúp tăng tính đồng thời khi xung đột ít, đồng thời yêu cầu hệ thống xác thực đúng các phụ thuộc và xử lý giao dịch bị hủy một cách an toàn. Mục tiêu cuối cùng vẫn là giữ kết quả tương đương với một thứ tự giao dịch tuần tự hợp lệ.

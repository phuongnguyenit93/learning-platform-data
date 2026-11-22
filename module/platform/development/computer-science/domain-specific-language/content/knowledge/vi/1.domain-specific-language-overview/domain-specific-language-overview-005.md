# DSL khai báo và DSL mệnh lệnh

Một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL) cung cấp cú pháp và khái niệm phù hợp với một miền bài toán cụ thể, chẳng hạn truy vấn dữ liệu, mô tả giao diện, cấu hình hạ tầng hoặc xây dựng phần mềm. Ngoài việc chọn từ vựng của miền, người thiết kế DSL còn phải quyết định người dùng sẽ mô tả công việc theo cách nào.

Hai phong cách phổ biến là **khai báo (declarative)** và **mệnh lệnh (imperative)**. Khác biệt cốt lõi nằm ở điều người viết phải nêu rõ: DSL khai báo tập trung vào kết quả hoặc các ràng buộc cần thỏa mãn; DSL mệnh lệnh tập trung vào những thao tác và thứ tự thực hiện để tạo ra kết quả đó.

Hai phong cách này là cách tổ chức ý nghĩa của chương trình, không phải hai loại cú pháp cố định. Một DSL có thể nghiêng về một phong cách, hoặc kết hợp cả hai.

## 1. Phân biệt hai phong cách

| Khía cạnh | DSL khai báo | DSL mệnh lệnh |
| --- | --- | --- |
| Câu hỏi chính | Muốn đạt trạng thái hoặc kết quả nào? | Cần thực hiện những bước nào? |
| Nội dung mô tả | Kết quả, quy tắc, điều kiện, quan hệ hoặc trạng thái mong muốn | Lệnh, thao tác, trình tự, nhánh rẽ và vòng lặp |
| Người viết quyết định | Ý nghĩa và điều kiện cần thỏa mãn | Cả ý nghĩa lẫn cách tiến hành từng bước |
| Vai trò của bộ thực thi | Tìm cách lập kế hoạch và thực hiện mô tả | Diễn giải hoặc chạy các thao tác theo luồng điều khiển đã mô tả |
| Điểm mạnh thường gặp | Ngắn gọn, dễ đọc ở mức mục tiêu, cho phép bộ thực thi tối ưu | Kiểm soát trình tự, xử lý quy trình nhiều bước và tác động phụ |
| Khó khăn thường gặp | Khó biểu đạt thuật toán hoặc thứ tự thao tác đặc thù | Dễ lộ chi tiết triển khai, khó thay đổi khi quy trình phức tạp |

Ví dụ đời thường: khi yêu cầu một dịch vụ sắp xếp các cuốn sách theo tên tác giả, ta có thể chỉ nêu tiêu chí sắp xếp. Đó là cách diễn đạt khai báo. Nếu ta chỉ rõ hãy đọc từng cuốn, lấy tên tác giả, so sánh với cuốn kế tiếp, đổi vị trí khi cần và lặp lại cho đến khi hết cuốn, ta đang mô tả theo cách mệnh lệnh.

Trong chương trình, sự khác biệt cũng tương tự. Với phong cách khai báo, người viết giao mục tiêu cho một bộ thực thi hiểu miền bài toán. Với phong cách mệnh lệnh, người viết mô tả quy trình mà bộ thực thi cần tiến hành.

## 2. DSL khai báo

### 2.1. Đặc điểm

DSL khai báo diễn đạt **điều cần có** hoặc **điều phải đúng**. Người viết nêu dữ liệu cần lấy, cấu trúc mong muốn, quy tắc áp dụng hoặc trạng thái đích. Bộ thực thi chịu trách nhiệm xác định cách đáp ứng mô tả đó.

Một DSL khai báo thường có các đặc điểm sau:

- Cú pháp xoay quanh đối tượng và khái niệm của miền, ví dụ bảng, cột, tài nguyên, thành phần giao diện hoặc phụ thuộc.
- Người dùng tập trung vào kết quả và các điều kiện; chi tiết thuật toán thường do hệ thống đảm nhiệm.
- Bộ thực thi có thể chọn kế hoạch khác nhau miễn là vẫn tuân thủ ngữ nghĩa đã định nghĩa.
- Thứ tự xuất hiện trong văn bản không nhất thiết là thứ tự thực hiện. Tuy nhiên, một số DSL vẫn quy định thứ tự ở những vị trí có ý nghĩa, chẳng hạn thứ tự ưu tiên của quy tắc CSS hoặc thứ tự các bước trong một cấu hình.

Khai báo không có nghĩa là hệ thống không thực hiện công việc. Trái lại, hệ thống vẫn phải phân tích mô tả, kiểm tra tính hợp lệ, lập kế hoạch và thực thi. Điểm khác biệt là người viết không phải chỉ định toàn bộ các bước nội bộ đó.

### 2.2. Ví dụ SQL

SQL là ví dụ quen thuộc về ngôn ngữ có phong cách khai báo khi truy vấn dữ liệu. Câu lệnh sau mô tả những hàng cần nhận:

~~~sql
SELECT order_id, customer_id, total
FROM orders
WHERE status = 'PAID'
  AND total >= 1000000
ORDER BY total DESC;
~~~

Người viết chỉ định:

- Lấy ba cột từ bảng orders.
- Chỉ chọn đơn hàng có trạng thái PAID và tổng tiền từ một triệu trở lên.
- Sắp xếp kết quả theo tổng tiền giảm dần.

Người viết không yêu cầu cơ sở dữ liệu phải quét bảng theo cách nào, dùng chỉ mục nào, nối dữ liệu theo thuật toán nào hoặc cấp phát bộ nhớ ra sao. Bộ tối ưu truy vấn của hệ quản trị cơ sở dữ liệu có thể lựa chọn kế hoạch thực thi dựa trên cấu trúc bảng, chỉ mục, thống kê và chi phí ước lượng. Kế hoạch đó có thể thay đổi giữa các lần chạy hoặc giữa các hệ quản trị cơ sở dữ liệu, trong khi ý nghĩa truy vấn vẫn được giữ nguyên.

SQL vẫn có những yếu tố mang tính thứ tự và thủ tục trong các phần mở rộng của nó. Ví dụ, ORDER BY quy định thứ tự của kết quả trả về; các thủ tục lưu trữ có thể chứa biến, điều kiện và vòng lặp. Vì vậy, nên nói SQL có phong cách khai báo nổi bật trong truy vấn quan hệ, thay vì khẳng định mọi câu lệnh SQL đều thuần khai báo.

### 2.3. Ví dụ CSS

CSS mô tả cách các phần tử tài liệu nên được trình bày:

~~~css
.card {
  display: grid;
  grid-template-columns: 12rem 1fr;
  gap: 1rem;
  align-items: center;
}

.card__title {
  font-size: 1.25rem;
  font-weight: 700;
}
~~~

Người viết mô tả quy tắc bố cục, khoảng cách và kiểu chữ. Trình duyệt tính toán kiểu cuối cùng bằng cách áp dụng cascade, kế thừa, độ ưu tiên và các quy tắc bố cục. Người viết không cần tự tính tọa độ từng phần tử rồi gọi các thao tác vẽ theo thứ tự.

CSS cho thấy một DSL khai báo có thể chứa nhiều quy tắc tương tác. Khi nhiều bộ chọn cùng tác động lên một phần tử, trình duyệt phải giải quyết độ ưu tiên theo ngữ nghĩa của CSS. Do đó, khai báo vẫn có quy tắc đánh giá rõ ràng; nó không đơn giản là một danh sách thuộc tính không có thứ tự.

### 2.4. Ví dụ mô tả trạng thái hạ tầng

Một cấu hình theo hướng khai báo có thể mô tả một máy chủ cần tồn tại với kích thước và ảnh hệ điều hành xác định:

~~~hcl
resource "example_server" "app" {
  name  = "application-server"
  image = "linux-stable"
  size  = "small"
}
~~~

Với một công cụ quản lý hạ tầng hỗ trợ mô hình này, người dùng mô tả tài nguyên mong muốn. Công cụ so sánh mô tả với trạng thái thực tế mà nó quan sát được, sau đó lập kế hoạch tạo mới hoặc cập nhật tài nguyên để tiến gần trạng thái đích. Cách triển khai cụ thể phụ thuộc vào công cụ và nhà cung cấp.

Ví dụ này cũng cho thấy khai báo thường phù hợp khi có thể mô tả trạng thái đích và để một bộ điều khiển chịu trách nhiệm đưa hệ thống đến trạng thái đó.

### 2.5. Ưu điểm và giới hạn

**Ưu điểm:**

- Người đọc dễ hiểu mục tiêu nghiệp vụ mà không cần lần theo từng bước kỹ thuật.
- Bộ thực thi có cơ hội tối ưu cách thực hiện mà không buộc người viết sửa mô tả.
- Cấu hình có thể ngắn gọn và nhất quán khi miền bài toán có các khái niệm ổn định.
- Có thể kiểm tra mô tả ở mức quy tắc hoặc trạng thái mong muốn trước khi thực thi.

**Giới hạn:**

- Người dùng ít kiểm soát trực tiếp thuật toán, thứ tự và chi tiết tác động phụ.
- Những quy trình có nhiều bước phụ thuộc hoặc cần xử lý ngoại lệ riêng có thể khó diễn đạt.
- Kết quả phụ thuộc đáng kể vào ngữ nghĩa và chất lượng của bộ thực thi.
- Một mô tả ngắn vẫn có thể gây hiểu nhầm nếu các quy tắc mặc định, độ ưu tiên hoặc trạng thái hiện tại không rõ ràng.

## 3. DSL mệnh lệnh

### 3.1. Đặc điểm

DSL mệnh lệnh diễn đạt **cách thực hiện công việc**. Người viết nêu các thao tác cần tiến hành và cách điều khiển luồng thực hiện. Một chương trình mệnh lệnh thường mô tả sự thay đổi trạng thái qua một chuỗi bước.

Các cấu trúc thường gặp gồm:

- Gán giá trị cho biến hoặc cập nhật trạng thái.
- Gọi thao tác trên đối tượng hoặc tài nguyên.
- Rẽ nhánh theo điều kiện.
- Lặp qua tập dữ liệu hoặc lặp cho đến khi đạt điều kiện dừng.
- Xử lý lỗi, hoàn tác hoặc thực hiện hành động bù khi một bước thất bại.

Với phong cách này, thứ tự có ý nghĩa trực tiếp. Thao tác ở bước sau có thể phụ thuộc vào kết quả hoặc tác động phụ của bước trước.

### 3.2. Ví dụ xử lý đơn hàng bằng thủ tục

Giả sử cần tính tổng tiền của các đơn hàng đã thanh toán. Có thể viết truy vấn SQL khai báo để cơ sở dữ liệu tính tổng:

~~~sql
SELECT SUM(total) AS paid_total
FROM orders
WHERE status = 'PAID';
~~~

Cũng có thể dùng một khối thủ tục PL/SQL để mô tả rõ quá trình duyệt từng đơn hàng và cộng dồn:

~~~sql
DECLARE
  v_paid_total NUMBER := 0;
BEGIN
  FOR rec IN (
    SELECT total
    FROM orders
    WHERE status = 'PAID'
  ) LOOP
    v_paid_total := v_paid_total + rec.total;
  END LOOP;

  DBMS_OUTPUT.PUT_LINE(v_paid_total);
END;
/
~~~

Trong ví dụ thủ tục, người viết chỉ rõ biến tích lũy, vòng lặp, thao tác cộng và lệnh xuất kết quả. Luồng thực hiện được thể hiện trực tiếp trong chương trình. Đây là phong cách mệnh lệnh trong cùng miền xử lý cơ sở dữ liệu.

Hai đoạn mã minh họa hai cách diễn đạt, nhưng không nhất thiết tương đương trong mọi tình huống thực tế. Ví dụ thủ tục có thể cần xử lý giá trị NULL, kiểu dữ liệu, lỗi hoặc yêu cầu giao dịch. Câu truy vấn tổng hợp thường để hệ quản trị cơ sở dữ liệu xử lý việc tính toán theo cách phù hợp với bộ máy truy vấn.

### 3.3. Ví dụ DSL xây dựng với Gradle

Gradle cung cấp DSL để mô tả quy trình xây dựng phần mềm. Trong Kotlin DSL, ta có thể khai báo một task và đặt hành động sẽ chạy khi task được thực thi:

~~~kotlin
tasks.register("printBuildMessage") {
    doLast {
        println("Building the application")
    }
}
~~~

Phần đăng ký task và cấu hình task sử dụng mô hình DSL của Gradle. Phần thân doLast chứa hành động được thực hiện khi task chạy. Khi hành động được mở rộng thành nhiều lệnh, điều kiện hoặc thao tác trên tệp, phần đó thể hiện rõ phong cách mệnh lệnh.

Ví dụ này cũng nhắc rằng một DSL thực tế có thể kết hợp nhiều phong cách: cấu hình đồ thị task và phụ thuộc mang tính khai báo, còn nội dung hành động bên trong task có thể mang tính mệnh lệnh.

### 3.4. Ưu điểm và giới hạn

**Ưu điểm:**

- Kiểm soát rõ trình tự và thời điểm của từng thao tác.
- Phù hợp với quy trình nhiều bước, có điều kiện, vòng lặp hoặc tương tác với hệ thống bên ngoài.
- Dễ diễn đạt các tác động phụ như ghi tệp, gửi yêu cầu mạng hoặc cập nhật trạng thái.
- Có thể chỉ rõ cách xử lý lỗi và hành động tiếp theo khi một bước không thành công.

**Giới hạn:**

- Người đọc phải theo dõi luồng điều khiển để hiểu kết quả cuối cùng.
- Nhiều chi tiết thao tác có thể làm chương trình dài và khó bảo trì.
- Thay đổi cách thực hiện có thể đòi hỏi sửa nhiều bước.
- Việc tối ưu hóa tự động khó hơn khi chương trình quy định chặt thứ tự và tác động phụ.

## 4. So sánh hai cách diễn đạt trên cùng một bài toán

Xét yêu cầu: lấy tên và tổng tiền của các khách hàng có đơn hàng đã thanh toán, sau đó sắp xếp theo tổng tiền giảm dần.

Với cách khai báo, ta nêu quan hệ dữ liệu, điều kiện lọc, phép tổng hợp và thứ tự kết quả:

~~~sql
SELECT c.customer_id,
       c.name,
       SUM(o.total) AS paid_total
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.name
ORDER BY paid_total DESC;
~~~

Câu lệnh thể hiện kết quả cần nhận. Hệ quản trị cơ sở dữ liệu quyết định cách đọc bảng, chọn chỉ mục, nối hai bảng và tính tổng.

Với cách mệnh lệnh, chương trình có thể thực hiện các bước khái quát sau:

1. Tạo cấu trúc lưu tổng tiền theo khách hàng.
2. Đọc các đơn hàng đã thanh toán.
3. Với mỗi đơn hàng, xác định khách hàng tương ứng.
4. Cộng tổng tiền đơn hàng vào giá trị của khách hàng đó.
5. Chuyển các giá trị đã cộng dồn thành danh sách kết quả.
6. Sắp xếp danh sách theo tổng tiền giảm dần.
7. Xuất danh sách.

Cách mệnh lệnh cho thấy rõ thuật toán và thứ tự thao tác. Tuy nhiên, người viết phải tự chịu trách nhiệm về cấu trúc lưu trữ, xử lý dữ liệu thiếu, hiệu năng, việc sắp xếp và các trường hợp lỗi. Cách khai báo ngắn hơn vì giao những quyết định thực thi đó cho hệ quản trị cơ sở dữ liệu.

Đây không phải quy tắc rằng khai báo luôn tốt hơn hoặc mệnh lệnh luôn chậm hơn. Một bộ thực thi khai báo có thể chọn kế hoạch kém nếu thống kê hoặc cấu hình không tốt; một thuật toán mệnh lệnh được thiết kế cẩn thận có thể phù hợp hơn với một quy trình đặc thù. Cần đánh giá theo yêu cầu và môi trường thực tế.

## 5. DSL kết hợp khai báo và mệnh lệnh

Nhiều DSL trong thực tế không nằm hoàn toàn ở một phía. Chúng dùng phần khai báo để mô tả cấu trúc, mục tiêu hoặc phụ thuộc, đồng thời cho phép phần mệnh lệnh xử lý những hành động đặc thù.

Ví dụ:

- **Gradle:** khai báo plugin, dependency và quan hệ phụ thuộc giữa các task; các action bên trong task có thể chứa lệnh tuần tự.
- **Make:** khai báo mục tiêu và quan hệ phụ thuộc giữa các tệp; recipe của mỗi mục tiêu chứa các lệnh cần chạy.
- **Ansible:** playbook mô tả máy chủ và các task theo cấu trúc khai báo; nhiều module hướng đến trạng thái mong muốn, trong khi thứ tự task, điều kiện và vòng lặp điều khiển quy trình.
- **SQL và PL/SQL:** câu truy vấn thường khai báo dữ liệu cần lấy; thủ tục có thể dùng biến, vòng lặp và nhánh điều kiện để điều phối công việc.

Khi một DSL hỗ trợ cả hai phong cách, cần hiểu ranh giới của từng phần. Phần khai báo thường thuận lợi để bộ thực thi lập kế hoạch, kiểm tra phụ thuộc hoặc quản lý trạng thái. Phần mệnh lệnh hữu ích khi cần một trình tự cụ thể, thao tác có tác động phụ hoặc logic điều khiển mà phần khai báo không biểu đạt rõ.

Không nên chỉ dựa vào hình thức bề ngoài để phân loại. Một tệp cấu hình có dấu ngoặc và khối lệnh chưa chắc là mệnh lệnh; một đoạn mã ngắn cũng chưa chắc là khai báo. Cần xem ngữ nghĩa của DSL: người viết đang nêu trạng thái/kết quả hay đang chỉ định các bước thực hiện?

## 6. Chọn phong cách phù hợp

Có thể dùng các câu hỏi sau để chọn cách thiết kế hoặc sử dụng DSL:

| Câu hỏi | Nghiêng về khai báo | Nghiêng về mệnh lệnh |
| --- | --- | --- |
| Có thể mô tả rõ trạng thái hoặc kết quả mong muốn không? | Có | Không đủ rõ |
| Bộ thực thi có đủ hiểu biết để tự chọn cách làm không? | Có | Không |
| Thứ tự thao tác có ảnh hưởng trực tiếp đến ý nghĩa không? | Ít hoặc có thể ẩn đi | Có |
| Quy trình có nhiều nhánh, vòng lặp và tác động phụ riêng không? | Ít | Nhiều |
| Có muốn thay đổi cách tối ưu mà không sửa mô tả không? | Có | Không phải ưu tiên chính |
| Có cần kiểm soát chi tiết từng bước để tích hợp hệ thống khác không? | Ít | Có |

**Ưu tiên khai báo** khi miền bài toán có thể được mô tả tốt bằng quy tắc, quan hệ, truy vấn hoặc trạng thái đích. Ví dụ: lọc dữ liệu, định nghĩa giao diện, mô tả phụ thuộc và cấu hình tài nguyên.

**Ưu tiên mệnh lệnh** khi công việc phụ thuộc vào trình tự thao tác, cần điều kiện và vòng lặp cụ thể, hoặc phải điều phối nhiều tác động phụ. Ví dụ: di chuyển dữ liệu qua nhiều bước, xử lý tệp theo quy tắc riêng hoặc thực hiện quy trình tích hợp có nhiều nhánh.

**Kết hợp hai phong cách** khi phần lớn yêu cầu có thể mô tả ở mức mục tiêu nhưng vẫn có một số bước cần điều khiển trực tiếp. Nên giữ phần khai báo ở nơi bộ thực thi có thể quản lý và tối ưu, còn phần mệnh lệnh chỉ đảm nhiệm logic thực sự cần thiết.

Khi thiết kế DSL mới, lựa chọn này cần được quyết định cùng với ngữ nghĩa và mô hình thực thi. Một DSL khai báo cần định nghĩa rõ các quy tắc, cách giải quyết xung đột, giá trị mặc định và cách chuyển mô tả thành kế hoạch. Một DSL mệnh lệnh cần định nghĩa rõ thứ tự thực hiện, phạm vi trạng thái, cách xử lý lỗi và ý nghĩa của từng thao tác. Nếu DSL kết hợp cả hai, tài liệu phải chỉ rõ phần nào được đánh giá khi cấu hình và phần nào chỉ chạy khi thực thi.

## 7. Những nhầm lẫn thường gặp

**“Khai báo nghĩa là không có thứ tự.”** Không chính xác. Một DSL khai báo vẫn có thể quy định thứ tự kết quả hoặc thứ tự ưu tiên. SQL có ORDER BY; CSS có quy tắc cascade. Điều quan trọng là người viết không phải mô tả toàn bộ trình tự thao tác nội bộ.

**“Khai báo không có thuật toán.”** Không chính xác. Bộ thực thi vẫn phải dùng thuật toán để đáp ứng mô tả. Chẳng hạn, hệ quản trị cơ sở dữ liệu lập kế hoạch truy vấn và chọn cách nối bảng. Thuật toán nằm ở bộ thực thi thay vì được người dùng DSL chỉ định trực tiếp.

**“Mệnh lệnh luôn là ngôn ngữ cấp thấp.”** Không chính xác. Một DSL mệnh lệnh vẫn có thể cung cấp thao tác ở mức trừu tượng cao, chẳng hạn tạo tài nguyên, gửi thông điệp hoặc triển khai dịch vụ. Mệnh lệnh nói về cách diễn đạt quy trình, không quyết định mức trừu tượng.

**“Một ngôn ngữ chỉ có thể thuộc một phong cách.”** Không chính xác. Nhiều hệ thống kết hợp cấu hình khai báo với các khối hành động mệnh lệnh. Cần phân loại theo phần ngữ nghĩa đang xét.

**“Khai báo và mệnh lệnh đồng nghĩa với DSL và ngôn ngữ đa dụng.”** Không chính xác. Đây là hai trục phân biệt khác nhau. DSL được xác định bởi phạm vi miền mà nó phục vụ; khai báo hay mệnh lệnh mô tả cách chương trình diễn đạt công việc. Một DSL có thể khai báo hoặc mệnh lệnh, và một ngôn ngữ đa dụng cũng có thể hỗ trợ cả hai phong cách.

## 8. Kết luận

DSL khai báo cho phép người dùng mô tả kết quả, quy tắc hoặc trạng thái mong muốn và giao cho bộ thực thi quyết định cách đáp ứng. DSL mệnh lệnh cho phép người dùng chỉ rõ chuỗi thao tác, điều kiện và vòng lặp để tạo ra kết quả. Phong cách khai báo thường giúp mô tả mục tiêu gọn và tạo cơ hội tối ưu hóa; phong cách mệnh lệnh thường đem lại khả năng kiểm soát quy trình và tác động phụ.

Khi đọc hoặc thiết kế một DSL, hãy xem xét ngữ nghĩa của câu lệnh và vai trò của bộ thực thi. Nếu câu lệnh trả lời câu hỏi “cần đạt điều gì?”, nó nghiêng về khai báo. Nếu câu lệnh trả lời “cần làm những bước nào?”, nó nghiêng về mệnh lệnh. Khi một hệ thống cần cả hai, hãy xác định rõ ranh giới để chương trình vẫn dễ hiểu, dễ kiểm tra và dễ bảo trì.


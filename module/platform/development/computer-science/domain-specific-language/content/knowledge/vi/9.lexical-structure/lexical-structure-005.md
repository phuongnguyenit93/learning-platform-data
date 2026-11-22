# Toán tử

Trong ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL), người dùng thường cần kết hợp giá trị, so sánh đối tượng, kiểm tra điều kiện và mô tả phép biến đổi theo cách ngắn gọn. **Toán tử (operator)** là ký hiệu hoặc từ khóa biểu thị một phép toán hay quan hệ được áp dụng lên một hoặc nhiều toán hạng (operand) để tạo ra kết quả hoặc xác định hành vi.

Ví dụ, trong biểu thức `tong_tien >= 500000 VND`, toán tử `>=` so sánh hai giá trị tiền tệ và trả về kết quả logic. Trong `so_luong * don_gia`, toán tử `*` nhân hai toán hạng. Trong `trang_thai IN {MOI_TAO, DA_XAC_NHAN}`, toán tử `IN` kiểm tra một giá trị có thuộc tập hợp được chỉ định hay không.

Toán tử thuộc từ vựng và cú pháp của DSL, nhưng ý nghĩa của nó phải được định nghĩa trong ngữ nghĩa ngôn ngữ. Cùng một ký hiệu có thể mang ý nghĩa khác nhau giữa các DSL. Chẳng hạn, `+` có thể cộng số, cộng tiền cùng loại tiền tệ, nối chuỗi hoặc ghép danh sách. Vì vậy, thiết kế toán tử không chỉ là chọn ký hiệu dễ gõ; nó còn phải quy định kiểu toán hạng, kiểu kết quả, thứ tự đánh giá, độ ưu tiên, tính kết hợp, trường hợp lỗi và những giới hạn miền.

## 1. Toán tử và toán hạng

Một biểu thức toán tử thường có ba thành phần: toán tử, toán hạng và kết quả. Toán hạng là giá trị hoặc biểu thức mà toán tử tác động lên. Kết quả là giá trị được tạo ra theo ngữ nghĩa đã định nghĩa.

Ví dụ:

```text
gia_tri_don_hang + phi_van_chuyen
       ^          ^          ^
   toán hạng   toán tử    toán hạng
```

Biểu thức trên dùng hai toán hạng và một toán tử. Mỗi toán hạng có thể là một giá trị hằng, một biến, một thuộc tính miền, một lời gọi hàm hoặc một biểu thức lồng nhau.

### 1.1. Số lượng toán hạng

Toán tử được phân loại theo số lượng toán hạng mà nó nhận:

- **Toán tử một ngôi (unary):** Nhận một toán hạng, ví dụ `-x` hoặc `NOT dieu_kien`.
- **Toán tử hai ngôi (binary):** Nhận hai toán hạng, ví dụ `a + b`, `x >= y` hoặc `A AND B`.
- **Toán tử ba ngôi (ternary):** Nhận ba thành phần, thường dùng để chọn kết quả theo điều kiện, ví dụ `dieu_kien ? gia_tri_dung : gia_tri_sai`.
- **Toán tử nhiều ngôi:** Một số DSL có toán tử hoặc cấu trúc cú pháp nhận nhiều hơn ba toán hạng, chẳng hạn phép kiểm tra một giá trị nằm trong danh sách.

Số lượng toán hạng ảnh hưởng đến cách parser nhận diện biểu thức và cách runtime đánh giá nó. Một từ khóa có thể được dùng ở nhiều dạng nếu ngữ pháp quy định rõ, nhưng nên tránh làm cho người đọc khó phân biệt vai trò.

### 1.2. Vị trí toán tử

Toán tử có thể xuất hiện trước, giữa hoặc sau toán hạng:

| Dạng | Ví dụ | Đặc điểm |
|---|---|---|
| Tiền tố (prefix) | `-so_du`, `NOT hop_le` | Toán tử đứng trước toán hạng |
| Trung tố (infix) | `gia_tri + phi`, `a >= b` | Toán tử đứng giữa các toán hạng |
| Hậu tố (postfix) | `gia_tri!`, `doi_tuong?` | Toán tử đứng sau toán hạng |

DSL thường dùng dạng trung tố cho phép toán số học và so sánh vì gần với cách viết toán học. Dạng tiền tố phù hợp với phủ định logic hoặc dấu âm. Dạng hậu tố ít phổ biến hơn và chỉ nên dùng khi có quy ước rõ ràng.

### 1.3. Toán tử khác với hàm và từ khóa

Toán tử, hàm và từ khóa đều có thể biểu đạt thao tác, nhưng cách dùng khác nhau:

- Toán tử thường xuất hiện trong biểu thức với vị trí và độ ưu tiên được quy định, ví dụ `a + b`.
- Hàm thường có tên và danh sách tham số, ví dụ `tinh_phi(a, b)`.
- Từ khóa thường xác định cấu trúc hoặc điều khiển ngôn ngữ, ví dụ `IF`, `THEN`, `RULE`.

Ranh giới không tuyệt đối. `IN` có thể được thiết kế như một toán tử trung tố hoặc như một hàm `contains(collection, value)`. Điều quan trọng là hình thức phải nhất quán, dễ đọc và có ngữ nghĩa được tài liệu hóa.

## 2. Các nhóm toán tử thường gặp

Một DSL có thể hỗ trợ nhiều nhóm toán tử, nhưng chỉ nên đưa vào những nhóm cần thiết cho nhiệm vụ của miền. Một DSL mô tả chính sách có thể cần số học, so sánh và logic; DSL truy vấn có thể cần toán tử tập hợp, chuỗi và thành viên; DSL lịch có thể cần toán tử thời gian và khoảng.

### 2.1. Toán tử số học

Toán tử số học thực hiện phép tính trên các giá trị số hoặc kiểu đại lượng tương thích.

| Toán tử | Tên | Ví dụ | Ý nghĩa |
|---|---|---|---|
| `+` | Cộng | `a + b` | Tổng hai giá trị |
| `-` | Trừ | `a - b` | Hiệu hai giá trị |
| `*` | Nhân | `a * b` | Tích hai giá trị |
| `/` | Chia | `a / b` | Thương của phép chia |
| `%` | Chia lấy dư | `a % b` | Phần dư khi chia số nguyên hoặc kiểu được hỗ trợ |
| `-x` | Đổi dấu | `-so_du` | Đối của một giá trị số |
| `+x` | Dấu dương | `+so_luong` | Biểu thị giá trị dương hoặc giữ nguyên giá trị |

Ví dụ trong DSL tính phí:

```text
tong_phi = phi_co_ban + so_km * phi_moi_km
```

Nếu `phi_co_ban` và `phi_moi_km` có kiểu tiền tệ, còn `so_km` là số vô hướng, runtime cần định nghĩa phép nhân giữa khoảng cách và đơn giá theo kilomet. Không nên cho phép mọi phép toán số học chỉ vì các giá trị có thể chuyển thành số.

Các vấn đề cần quy định:

- Chia cho 0 tạo lỗi hay giá trị đặc biệt?
- Phép chia số nguyên làm tròn xuống, làm tròn về 0 hay trả số thập phân?
- Phép `%` hoạt động với số âm như thế nào?
- Tràn số được báo lỗi hay bão hòa ở giới hạn kiểu?
- Số thập phân được lưu với độ chính xác và quy tắc làm tròn nào?
- Kiểu đại lượng có đơn vị được kết hợp ra sao?

### 2.2. Toán tử so sánh

Toán tử so sánh xác định quan hệ giữa hai giá trị và thường trả về kiểu Boolean (`true` hoặc `false`).

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `==` | Bằng | `trang_thai == DA_GIAO` |
| `!=` | Khác | `ma_khu_vuc != null` |
| `>` | Lớn hơn | `tong_tien > 500000 VND` |
| `<` | Nhỏ hơn | `tuoi < 18` |
| `>=` | Lớn hơn hoặc bằng | `so_luong >= 1` |
| `<=` | Nhỏ hơn hoặc bằng | `khoang_cach <= 10 km` |

Ngữ nghĩa so sánh phụ thuộc kiểu. Hai giá trị số có thể được so sánh theo thứ tự số học; chuỗi có thể so sánh theo thứ tự từ điển nếu DSL hỗ trợ; ngày giờ có thể so sánh theo dòng thời gian; trạng thái enum thường chỉ hỗ trợ bằng hoặc khác.

Ví dụ:

```text
neu tong_tien >= 500000 VND {
    mien_phi_giao_hang()
}
```

Toán tử `>=` bao gồm trường hợp đúng bằng ngưỡng. Nếu dùng `>`, đơn hàng có giá trị đúng 500.000 VND sẽ không thỏa điều kiện. Sự khác biệt này thường rất quan trọng trong quy tắc nghiệp vụ.

Không phải mọi kiểu đều có thứ tự tự nhiên. So sánh `>` giữa hai mã trạng thái như `MOI_TAO` và `DA_GIAO` không nên được cho phép nếu miền chưa định nghĩa thứ tự đó.

### 2.3. Toán tử logic

Toán tử logic kết hợp hoặc phủ định các điều kiện Boolean.

| Toán tử | Tên | Ví dụ | Ý nghĩa |
|---|---|---|---|
| `AND` | Và | `co_hang AND da_thanh_toan` | Đúng khi cả hai điều kiện đúng |
| `OR` | Hoặc | `khach_vip OR co_ma_uu_dai` | Đúng khi ít nhất một điều kiện đúng |
| `NOT` | Phủ định | `NOT da_huy` | Đảo giá trị logic |
| `XOR` | Hoặc loại trừ | `A XOR B` | Đúng khi đúng chính xác một điều kiện |

Ví dụ:

```text
co_the_giao = da_thanh_toan AND co_hang AND NOT dia_chi_bi_chan
```

`AND`, `OR` và `NOT` là các toán tử thường cần trong DSL quy tắc. `XOR` ít phổ biến hơn; nếu có, cần giải thích rõ để người dùng không nhầm nó với `OR` thông thường.

Một số DSL dùng ký hiệu `&&`, `||` và `!` thay cho từ khóa. Từ khóa thường dễ đọc với chuyên gia miền, trong khi ký hiệu ngắn có thể quen thuộc với lập trình viên. Lựa chọn cần phù hợp với người dùng mục tiêu.

### 2.4. Toán tử gán

Toán tử gán đưa một giá trị vào biến hoặc thuộc tính có thể thay đổi.

| Toán tử | Ví dụ | Ý nghĩa |
|---|---|---|
| `=` | `phi = 30000` | Gán giá trị |
| `+=` | `tong += phu_phi` | Cộng rồi gán lại |
| `-=` | `so_du -= so_tien` | Trừ rồi gán lại |
| `*=` | `so_luong *= he_so` | Nhân rồi gán lại |
| `/=` | `tong /= so_phan` | Chia rồi gán lại |

Không phải DSL nào cũng cần gán. DSL khai báo thường mô tả trạng thái mong muốn hoặc quan hệ mà không yêu cầu thay đổi biến tuần tự. Trong DSL đó, `=` có thể mang nghĩa khai báo thuộc tính hoặc xác định ràng buộc thay vì cập nhật trạng thái.

Ví dụ hai cách dùng có ý nghĩa khác nhau:

```text
# Gán trong ngôn ngữ mệnh lệnh
tong_phi = phi_co_ban + phu_phi

# Khai báo thuộc tính trong DSL cấu hình
may_chu {
    so_cpu = 4
}
```

Đặc tả cần nói rõ `=` là phép gán, phép định nghĩa hay phép so sánh bằng trong từng ngữ cảnh. Tránh dùng cùng ký hiệu với nhiều nghĩa mà parser và người đọc khó phân biệt.

### 2.5. Toán tử kiểm tra thành viên

Toán tử thành viên kiểm tra một giá trị có thuộc tập hợp, danh sách, khoảng hoặc nhóm giá trị hay không.

Ví dụ:

```text
trang_thai IN {MOI_TAO, DA_XAC_NHAN, DANG_GIAO}
ma_vung NOT IN danh_sach_vung_cam
ngay_giao IN khoang_ngay_hieu_luc
```

DSL có thể dùng `IN`, `NOT IN`, `CONTAINS`, `HAS` hoặc một cú pháp khác. Cần xác định rõ hướng quan hệ: `x IN danh_sach` và `danh_sach CONTAINS x` có thể biểu đạt cùng ý nghĩa nhưng đặt toán hạng ở vị trí khác nhau.

Với tập hợp, cần định nghĩa việc so sánh phần tử, xử lý phần tử trùng lặp và hành vi khi collection rỗng.

### 2.6. Toán tử trên chuỗi

DSL xử lý văn bản có thể hỗ trợ các phép toán:

- Nối chuỗi.
- Kiểm tra chuỗi chứa một đoạn con.
- Kiểm tra bắt đầu hoặc kết thúc bằng một tiền tố/hậu tố.
- So khớp theo mẫu.
- So sánh không phân biệt hoa thường.

Ví dụ:

```text
ten_khach_hang STARTS_WITH "Nguyen"
email CONTAINS "@example.com"
ma_don MATCHES "DH-[0-9]+"
```

Các toán tử chuỗi cần quy định chuẩn hóa Unicode, phân biệt chữ hoa/chữ thường, dấu tiếng Việt, khoảng trắng và quy tắc so khớp mẫu. Nếu `MATCHES` sử dụng regular expression, cần xác định cú pháp regex và giới hạn thời gian để tránh mẫu gây tiêu tốn tài nguyên quá mức.

### 2.7. Toán tử trên tập hợp và danh sách

Một DSL dữ liệu có thể cần các phép toán như hợp, giao, hiệu, nối danh sách hoặc kiểm tra tập con.

Ví dụ:

```text
vung_ap_dung = vung_noi_thanh UNION vung_ngoai_thanh
nhom_duoc_phep = nhom_a INTERSECT nhom_b
```

Các toán tử này thường có ngữ nghĩa khác nhau tùy kiểu collection. Danh sách có thứ tự và cho phép phần tử trùng; tập hợp thường không có thứ tự và không giữ phần tử trùng. Runtime cần giữ đúng đặc điểm kiểu dữ liệu thay vì áp dụng một phép toán chung thiếu định nghĩa.

### 2.8. Toán tử null và giá trị tùy chọn

Trong dữ liệu miền, một thuộc tính có thể chưa có giá trị. DSL có thể cung cấp các toán tử kiểm tra hoặc xử lý giá trị thiếu:

| Dạng minh họa | Ý nghĩa |
|---|---|
| `x == null` | Kiểm tra giá trị rỗng |
| `x != null` | Kiểm tra có giá trị |
| `x ?? fallback` | Dùng giá trị thay thế khi `x` không có |
| `x?.field` | Truy cập thuộc tính an toàn khi `x` có thể rỗng |
| `x IS PRESENT` | Kiểm tra giá trị hiện diện theo cú pháp miền |

Ví dụ:

```text
nguoi_nhan = don_hang.nguoi_nhan ?? don_hang.nguoi_mua
ten_khu_vuc = dia_chi?.khu_vuc?.ten
```

Các ký hiệu trên chỉ là ví dụ; một DSL không bắt buộc phải hỗ trợ tất cả. Cần phân biệt giá trị `null`, giá trị chưa biết, trường không tồn tại và trường không áp dụng. Nếu gộp chúng, biểu thức có thể cho kết quả không mong muốn.

### 2.9. Toán tử phạm vi và khoảng

DSL thời gian, lịch hoặc dữ liệu có thể cần biểu diễn khoảng giá trị:

```text
ngay IN 2026-01-01..2026-01-31
gia_tri IN [100000, 500000)
```

Ký hiệu khoảng phải quy định hai đầu có bao gồm hay không. `[a, b]` thường bao gồm cả hai đầu; `[a, b)` bao gồm đầu trái và loại đầu phải; `(a, b)` loại cả hai đầu. Nếu dùng `..`, cần nói rõ nó biểu diễn khoảng đóng, khoảng mở hay phụ thuộc ngữ cảnh.

### 2.10. Toán tử miền chuyên biệt

DSL có thể cung cấp toán tử có nghĩa trực tiếp trong lĩnh vực. Ví dụ:

| Miền | Toán tử minh họa | Ý nghĩa |
|---|---|---|
| Lịch và thời gian | `BEFORE`, `AFTER`, `OVERLAPS` | So sánh thời điểm hoặc khoảng thời gian |
| Địa lý | `WITHIN`, `NEAR`, `INTERSECTS` | Kiểm tra vị trí hoặc vùng địa lý |
| Quy trình | `TRANSITIONS_TO`, `PRECEDES` | Quan hệ giữa trạng thái hoặc bước |
| Phân quyền | `HAS_ROLE`, `CAN` | Kiểm tra vai trò hoặc khả năng |
| Tài chính | `IN_CURRENCY`, `CONVERTS_TO` | Kiểm tra hoặc chuyển đổi tiền tệ |
| Truy vấn | `CONTAINS`, `STARTS_WITH`, `MATCHES` | Lọc dữ liệu theo nội dung |

Ví dụ:

```text
lich_hen OVERLAPS khoang_bao_tri
diem_giao WITHIN khu_vuc_phuc_vu
don_hang TRANSITIONS_TO DA_GIAO
nguoi_dung HAS_ROLE QUAN_LY
```

Toán tử miền có thể giúp DSL gần với tư duy chuyên gia hơn. Tuy nhiên, mỗi toán tử cần một định nghĩa chính xác, kiểu toán hạng, kiểu kết quả và cách xử lý dữ liệu không đầy đủ.

## 3. Kiểu toán hạng và kiểu kết quả

Toán tử không chỉ có ký hiệu; nó có hợp đồng kiểu. Hợp đồng này xác định những kiểu nào được phép xuất hiện ở hai phía và kiểu nào được trả về.

Ví dụ:

| Toán tử | Kiểu toán hạng | Kiểu kết quả |
|---|---|---|
| `+` số học | Number, Number | Number |
| `+` chuỗi | String, String | String |
| `>=` | Hai giá trị cùng kiểu có thứ tự | Boolean |
| `AND` | Boolean, Boolean | Boolean |
| `IN` | Giá trị T, Collection<T> | Boolean |
| `??` | Optional<T>, T | T |
| `BEFORE` | DateTime, DateTime | Boolean |

Đây là các hợp đồng minh họa. Đặc tả DSL phải xác định kiểu thực tế và các quy tắc chuyển đổi.

### 3.1. Kiểm tra kiểu tĩnh

Nếu DSL có hệ thống kiểu tĩnh, compiler có thể phát hiện phép toán không hợp lệ trước khi chạy.

Ví dụ:

```text
"500000" >= 500000 VND
```

Nếu toán hạng trái là chuỗi và toán hạng phải là tiền tệ, compiler nên báo lỗi kiểu thay vì tự chuyển chuỗi thành số. Chuyển đổi ngầm có thể gây bất ngờ và phụ thuộc định dạng.

### 3.2. Kiểm tra kiểu động

DSL có kiểu động có thể kiểm tra kiểu tại runtime. Khi đó, biểu thức chỉ phát sinh lỗi nếu dữ liệu thực tế không tương thích.

Ví dụ, trường `gia_tri` được đọc từ dữ liệu đầu vào có thể chứa số hoặc chuỗi tùy bản ghi. Runtime cần báo lỗi rõ ràng khi thực hiện phép so sánh không hợp lệ.

### 3.3. Chuyển kiểu ngầm định

Một số DSL cho phép chuyển kiểu tự động, ví dụ số nguyên sang số thập phân. Cần xác định danh sách chuyển đổi được phép, thứ tự ưu tiên và khả năng mất dữ liệu.

Chuyển kiểu từ chuỗi sang số hoặc từ một đơn vị tiền tệ sang đơn vị khác thường cần được thực hiện tường minh vì có thể thất bại hoặc cần dữ liệu tỷ giá.

### 3.4. Kiểu miền và đơn vị đo

Kiểu miền giúp ngăn các phép toán có vẻ hợp lệ về mặt số học nhưng sai về ý nghĩa.

Ví dụ:

- `Money + Money` chỉ hợp lệ nếu cùng loại tiền hoặc có quy tắc quy đổi rõ.
- `Distance / Time` có thể tạo ra kiểu vận tốc.
- `Weight + Weight` hợp lệ nếu cùng đơn vị hoặc được chuẩn hóa.
- `Date + Duration` có thể tạo ra một thời điểm mới.
- `Date - Date` có thể tạo ra một khoảng thời gian.

Một DSL có hệ thống đơn vị tốt sẽ ngăn lỗi như cộng 5 kilomet với 3 kilogram dù cả hai đều có thể được lưu dưới dạng số.

## 4. Độ ưu tiên và tính kết hợp của toán tử

Khi biểu thức có nhiều toán tử, DSL cần quy định thứ tự thực hiện. Hai khái niệm quan trọng là **độ ưu tiên (precedence)** và **tính kết hợp (associativity)**.

### 4.1. Độ ưu tiên

Độ ưu tiên xác định toán tử nào được xử lý trước khi không có dấu ngoặc.

Ví dụ:

```text
2 + 3 * 4
```

Nếu `*` có độ ưu tiên cao hơn `+`, biểu thức được hiểu là:

```text
2 + (3 * 4) = 14
```

Nếu hai toán tử có cùng độ ưu tiên, tính kết hợp sẽ xác định cách nhóm toán hạng.

### 4.2. Tính kết hợp

Tính kết hợp quy định cách nhóm các toán tử cùng mức ưu tiên:

- **Kết hợp trái (left-associative):** `a - b - c` được hiểu là `(a - b) - c`.
- **Kết hợp phải (right-associative):** `a = b = c` có thể được hiểu là `a = (b = c)` nếu DSL cho phép.
- **Không kết hợp (non-associative):** Không cho phép nối liên tiếp, chẳng hạn `a < b < c`, trừ khi ngôn ngữ định nghĩa rõ cú pháp so sánh chuỗi.

Không nên giả định mọi toán tử đều kết hợp trái. Phép lũy thừa thường được một số ngôn ngữ định nghĩa kết hợp phải; phép so sánh chuỗi có thể bị cấm để tránh cách hiểu mơ hồ.

### 4.3. Bảng độ ưu tiên minh họa

Bảng sau chỉ là một cấu hình tham khảo cho DSL biểu thức. DSL cụ thể có thể dùng thứ tự khác.

| Mức | Nhóm toán tử | Ví dụ | Tính kết hợp thường gặp |
|---:|---|---|---|
| 1 | Truy cập thuộc tính, gọi hàm | `don_hang.tong_tien`, `f(x)` | Trái |
| 2 | Một ngôi | `-x`, `NOT A` | Phải |
| 3 | Nhân, chia, chia dư | `*`, `/`, `%` | Trái |
| 4 | Cộng, trừ | `+`, `-` | Trái |
| 5 | Phạm vi | `..` | Theo đặc tả |
| 6 | So sánh, thành viên | `==`, `<`, `IN` | Thường không kết hợp |
| 7 | AND | `AND` | Trái |
| 8 | OR, XOR | `OR`, `XOR` | Trái |
| 9 | Điều kiện | `? :` | Thường phải |
| 10 | Gán | `=`, `+=` | Thường phải |

### 4.4. Dùng dấu ngoặc để làm rõ ý định

Dấu ngoặc đơn cho phép người viết kiểm soát thứ tự nhóm biểu thức:

```text
(gia_hang + phi_dong_goi) * he_so_thue
```

Ngay cả khi DSL có bảng độ ưu tiên rõ, nên khuyến khích dùng dấu ngoặc trong biểu thức dài hoặc có nhiều điều kiện. Điều này giúp người đọc hiểu ý định nhanh hơn và giảm lỗi khi sửa chương trình.

### 4.5. Bảng độ ưu tiên là một phần của đặc tả

Parser và runtime phải tuân theo cùng một bảng độ ưu tiên. Nếu parser nhóm biểu thức theo một thứ tự nhưng evaluator thực hiện theo thứ tự khác, kết quả sẽ không nhất quán.

Nên có ví dụ chuẩn cho từng mức và cho các cặp toán tử liền kề. Khi thay đổi độ ưu tiên, cần xem đó là thay đổi ngữ nghĩa có thể phá vỡ chương trình hiện có.

## 5. Thứ tự đánh giá và đánh giá ngắn mạch

Độ ưu tiên cho biết cách nhóm biểu thức; thứ tự đánh giá cho biết toán hạng nào được tính trước. Hai khái niệm này có liên quan nhưng không giống nhau.

### 5.1. Thứ tự đánh giá toán hạng

Với biểu thức `f() + g()`, runtime cần quy định `f()` hay `g()` được gọi trước. Nếu cả hai hàm đều thuần và không có lỗi, thứ tự có thể không ảnh hưởng đến kết quả. Nếu hàm có tác động phụ, thứ tự có thể làm thay đổi trạng thái hệ thống.

Một DSL có thể quy định đánh giá từ trái sang phải để dễ dự đoán. Nếu cho phép tối ưu hóa hoặc thực thi song song, cần xác định giới hạn của những thay đổi được phép.

### 5.2. Đánh giá ngắn mạch

Toán tử logic `AND` và `OR` thường có thể dừng đánh giá sớm:

- `A AND B`: nếu A là false, kết quả chắc chắn false nên B không cần đánh giá.
- `A OR B`: nếu A là true, kết quả chắc chắn true nên B không cần đánh giá.

Ví dụ:

```text
nguoi_dung != null AND nguoi_dung.co_quyen("DUYET")
```

Nếu vế trái false và DSL định nghĩa `AND` đánh giá ngắn mạch, runtime không gọi `co_quyen` trên đối tượng null.

### 5.3. Tác động phụ và short-circuit

Giả sử `ghi_nhat_ky()` có tác động phụ:

```text
da_huy AND ghi_nhat_ky()
```

Nếu `da_huy` false, short-circuit có thể khiến `ghi_nhat_ky()` không chạy. Người viết cần hiểu điều này. Tốt nhất, toán tử logic nên dùng với biểu thức thuần; tác động phụ nên được đặt trong câu lệnh riêng để tránh hành vi khó đoán.

### 5.4. Giá trị chưa biết trong logic ba trạng thái

Một số DSL truy vấn hoặc quy tắc cần ba giá trị logic: true, false và unknown. Điều này xảy ra khi dữ liệu thiếu hoặc điều kiện chưa thể xác định.

Ví dụ, nếu `ngay_giao` chưa có, biểu thức `ngay_giao < hom_nay` có thể cho `unknown` thay vì false. Khi kết hợp với AND/OR, DSL phải định nghĩa bảng chân trị tương ứng.

Nếu dùng logic hai trạng thái, DSL cần quy định rõ cách chuyển dữ liệu thiếu thành true hoặc false, hoặc báo lỗi. Không nên để từng hàm xử lý null theo cách riêng.

## 6. Toán tử miền và nạp chồng toán tử

Một DSL có thể định nghĩa cùng một ký hiệu hoạt động trên nhiều kiểu dữ liệu. Cách làm này gọi là **nạp chồng toán tử (operator overloading)**.

### 6.1. Nạp chồng có kiểm soát

Ví dụ, `+` có thể được định nghĩa cho:

```text
3 + 4                         # cộng số
"xin " + "chao"              # nối chuỗi nếu DSL cho phép
100000 VND + 20000 VND        # cộng tiền cùng loại tiền tệ
```

Mỗi trường hợp cần hợp đồng kiểu riêng. Không nên cho phép `+` giữa mọi kiểu chỉ vì có thể tạo một kết quả nào đó.

### 6.2. Khi nào nên tạo toán tử miền?

Toán tử miền hữu ích khi một phép quan hệ xuất hiện thường xuyên và có ý nghĩa ổn định trong lĩnh vực. Ví dụ `OVERLAPS` trong lịch biểu có thể dễ hiểu hơn một biểu thức gồm nhiều phép so sánh ngày giờ.

Nên dùng hàm thay vì toán tử khi thao tác có nhiều tham số, có nhiều bước hoặc có tác động phụ phức tạp. Ví dụ `tinh_phi_van_chuyen(don_hang, bang_gia, khu_vuc)` có thể dễ hiểu hơn khi được biểu diễn bằng hàm.

### 6.3. Tránh nạp chồng gây bất ngờ

Không nên để cùng ký hiệu có ý nghĩa quá khác nhau giữa các kiểu. Nếu `+` cộng tiền ở một trường hợp nhưng lại nối danh sách theo quy tắc khó dự đoán, người dùng cần phải học nhiều ngoại lệ.

Nếu hai phép toán có ý nghĩa miền khác nhau, dùng từ khóa hoặc hàm riêng thường rõ hơn.

### 6.4. Nạp chồng và phân giải kiểu

Khi có nhiều phiên bản toán tử, compiler cần xác định phiên bản phù hợp dựa trên kiểu toán hạng. Nếu có nhiều ứng viên cùng phù hợp, ngôn ngữ cần quy tắc ưu tiên rõ hoặc báo lỗi mơ hồ.

Không nên chọn ngầm một phép toán chỉ dựa trên chuyển kiểu không rõ ràng. Ví dụ `Money + Number` có thể có nhiều cách hiểu: cộng số tiền, cộng số đơn vị nhỏ nhất hoặc cộng tỷ lệ. DSL cần yêu cầu đơn vị rõ ràng.

## 7. Toán tử và ngữ nghĩa khai báo

Trong DSL khai báo, một biểu thức thường mô tả quan hệ hoặc điều kiện mà hệ thống cần thỏa mãn, không nhất thiết yêu cầu thực hiện phép tính tuần tự.

Ví dụ:

```text
may_chu.cpu >= 4
don_hang.trang_thai IN {DA_THANH_TOAN, DANG_GIAO}
lich_bao_tri OVERLAPS lich_trien_khai
```

Các biểu thức này có thể được dùng làm ràng buộc, bộ lọc hoặc điều kiện lựa chọn. Runtime có thể chuyển chúng thành truy vấn, bộ kiểm tra hoặc kế hoạch thực thi.

### 7.1. Biểu thức điều kiện

Biểu thức điều kiện thường có kiểu Boolean hoặc kiểu logic ba trạng thái. Chúng được dùng trong `IF`, `WHEN`, `WHERE`, `ASSERT` hoặc các cấu trúc tương tự.

### 7.2. Biểu thức ràng buộc

Ràng buộc mô tả điều kiện phải luôn đúng trong mô hình hợp lệ:

```text
assert don_hang.tong_tien >= 0 VND
assert ngay_ket_thuc >= ngay_bat_dau
```

Runtime hoặc validator kiểm tra ràng buộc và báo lỗi khi dữ liệu vi phạm.

### 7.3. Biểu thức truy vấn

Toán tử so sánh, thành viên và chuỗi có thể được dùng để lọc tập dữ liệu:

```text
where don_hang.trang_thai == DA_GIAO
  AND don_hang.tong_tien >= 500000 VND
```

Nếu DSL dịch biểu thức sang SQL hoặc hệ truy vấn khác, cần bảo đảm ngữ nghĩa hai bên tương đương, đặc biệt với null, collation chuỗi, số thập phân và múi giờ.

## 8. Thiết kế cú pháp toán tử

Toán tử là một phần dễ nhận thấy của DSL. Cú pháp nên cân bằng giữa sự quen thuộc, khả năng đọc và mức độ chính xác.

### 8.1. Ký hiệu hay từ khóa

Ký hiệu như `+`, `>=`, `&&` ngắn và quen thuộc với lập trình viên. Từ khóa như `AND`, `IN`, `BEFORE` có thể dễ đọc với chuyên gia miền và không phụ thuộc nhiều vào ký tự đặc biệt.

| Tiêu chí | Ký hiệu | Từ khóa |
|---|---|---|
| Độ ngắn | Thường ngắn | Có thể dài hơn |
| Khả năng đọc | Quen thuộc với người viết mã | Gần ngôn ngữ mô tả |
| Hỗ trợ bàn phím | Một số ký hiệu khó nhập trên bố cục bàn phím khác nhau | Dễ nhập nếu dùng bảng chữ cái phổ biến |
| Phân tích cú pháp | Cần xử lý ký tự và tổ hợp ký hiệu | Cần nhận diện từ khóa và ranh giới từ |
| Mở rộng miền | Có giới hạn số ký hiệu dễ nhớ | Có thể đặt tên theo nghiệp vụ |

Không cần chọn một kiểu cho toàn bộ DSL. Có thể dùng ký hiệu cho số học và từ khóa cho quan hệ miền, miễn là nhất quán.

### 8.2. Cú pháp dạng hàm so với dạng trung tố

Cùng một phép kiểm tra có thể viết theo nhiều cách:

```text
gia_tri IN tap_hop
contains(tap_hop, gia_tri)
tap_hop.contains(gia_tri)
```

Dạng trung tố có thể gần cách đọc tự nhiên. Dạng hàm dễ mở rộng khi có nhiều tham số hoặc tùy chọn. Dạng phương thức phù hợp với DSL nhúng trong ngôn ngữ hướng đối tượng.

### 8.3. Tránh ký hiệu quá tải

Nếu một ký hiệu đã có nghĩa phổ biến trong ngôn ngữ, việc gán nghĩa mới có thể gây nhầm. Ví dụ `!` thường là phủ định hoặc gợi ý một phép đặc biệt tùy ngôn ngữ. Nếu DSL dùng `!` để đánh dấu trạng thái bắt buộc, cần cân nhắc khả năng người dùng hiểu sai.

### 8.4. Từ khóa dành riêng và định danh

Nếu `IN`, `AND` hoặc `BEFORE` là từ khóa, cần quy định chúng có được dùng làm tên biến hay không. Parser cũng cần xử lý chữ hoa/chữ thường nhất quán.

Ví dụ, DSL có thể không phân biệt hoa thường với từ khóa nhưng vẫn phân biệt tên trường, hoặc yêu cầu tất cả từ khóa viết thường. Quy tắc này cần được tài liệu hóa.

## 9. Toán tử trong DSL nhúng và DSL độc lập

Hình thức triển khai DSL ảnh hưởng đến khả năng định nghĩa toán tử.

### 9.1. DSL độc lập

DSL độc lập có parser và ngữ pháp riêng nên nhóm thiết kế có thể kiểm soát ký hiệu, độ ưu tiên, tính kết hợp và cách xử lý lỗi. Đổi lại, nhóm phải triển khai lexer, parser, tài liệu và công cụ hỗ trợ.

### 9.2. DSL nhúng

DSL nhúng dựa vào cú pháp của ngôn ngữ chủ. Ví dụ, DSL trong Java có thể dùng phương thức `and()`, `or()` hoặc `greaterThan()` để biểu diễn phép toán vì Java không cho thư viện tự định nghĩa toán tử mới.

Một DSL nhúng trong Kotlin hoặc Scala có thể tận dụng một số khả năng cú pháp của ngôn ngữ chủ, nhưng vẫn bị giới hạn bởi quy tắc của ngôn ngữ đó. Không nên giả định mọi ngôn ngữ chủ đều cho phép định nghĩa toán tử tùy ý.

### 9.3. Độ ưu tiên kế thừa từ ngôn ngữ chủ

DSL nhúng thường phải chấp nhận độ ưu tiên và tính kết hợp của ngôn ngữ chủ. Nếu điều đó khiến biểu thức khó hiểu, nên dùng hàm hoặc phương thức có tên rõ thay vì cố tạo cú pháp giống ngôn ngữ độc lập.

## 10. Phân tích cú pháp biểu thức toán tử

Parser phải chuyển chuỗi toán tử thành cấu trúc biểu thức đúng theo ngữ pháp và độ ưu tiên.

### 10.1. Cây cú pháp biểu thức

Ví dụ:

```text
a + b * c
```

Nếu phép nhân ưu tiên cao hơn phép cộng, AST có dạng:

```text
        (+)
       /   \
      a    (*)
          /   \
         b     c
```

AST giúp runtime đánh giá theo cấu trúc đã phân tích thay vì phải suy đoán lại từ văn bản.

### 10.2. Recursive descent và precedence climbing

Parser có thể dùng nhiều kỹ thuật để xử lý biểu thức:

- **Recursive descent:** Mỗi mức ngữ pháp có thể được triển khai bằng một hàm phân tích riêng.
- **Precedence climbing:** Dùng mức ưu tiên để phân tích các toán tử trung tố theo thứ tự.
- **Pratt parser:** Dùng binding power hoặc quy tắc tiền tố/trung tố để xử lý nhiều dạng biểu thức linh hoạt.
- **Shunting-yard:** Chuyển biểu thức trung tố thành dạng hậu tố hoặc cây biểu thức dựa trên ngăn xếp toán tử.

Lựa chọn phụ thuộc độ phức tạp ngữ pháp, khả năng mở rộng và công cụ parser đang dùng.

### 10.3. Phân biệt dấu âm và phép trừ

Ký tự `-` có thể là toán tử một ngôi trong `-x` hoặc toán tử hai ngôi trong `a - b`. Lexer thường nhận cùng một token; parser xác định vai trò dựa trên vị trí cú pháp.

Ví dụ `a * -b` cần được phân tích thành phép nhân giữa `a` và giá trị đối của `b`. Ngữ pháp phải cho phép toán tử một ngôi ở vị trí phù hợp.

### 10.4. So sánh chuỗi và cú pháp phạm vi

Một số DSL cho phép viết `a < b < c`. Cú pháp này có thể được hiểu là `(a < b) AND (b < c)` hoặc `(a < b) < c`, hai cách hoàn toàn khác nhau về kiểu và ngữ nghĩa.

Nếu muốn hỗ trợ so sánh chuỗi, đặc tả phải nói rõ toán hạng giữa có được đánh giá một lần hay hai lần. Nếu không cần, nên cấm cú pháp đó và yêu cầu người dùng viết `a < b AND b < c`.

## 11. Lỗi và chẩn đoán liên quan đến toán tử

Toán tử có thể gây lỗi ở giai đoạn parse, kiểm tra kiểu hoặc runtime.

| Lỗi | Ví dụ | Cách xử lý phù hợp |
|---|---|---|
| Thiếu toán hạng | `a +` | Báo lỗi cú pháp tại vị trí toán tử |
| Sai số lượng toán hạng | `NOT a b` | Báo cấu trúc không hợp lệ |
| Không tương thích kiểu | `Money + Date` | Báo lỗi kiểu và nêu kiểu mong đợi |
| Chia cho 0 | `tong / 0` | Báo lỗi runtime hoặc quy tắc số học đã định nghĩa |
| So sánh không hỗ trợ | `trang_thai > DA_GIAO` | Báo không có thứ tự cho kiểu trạng thái |
| Giá trị thiếu | `null >= 10` | Áp dụng ngữ nghĩa null hoặc báo lỗi |
| Toán tử không xác định | `a %% b` | Báo ký hiệu không được hỗ trợ |
| Biểu thức mơ hồ | `a < b < c` | Báo cú pháp không được phép hoặc giải thích quy tắc |

Thông báo lỗi nên chỉ ra vị trí, toán tử, kiểu toán hạng thực tế và kiểu được chấp nhận. Ví dụ:

```text
DSL-E-OPERATOR-012: Toán tử '+' không hỗ trợ Money và Distance.
Tại: policy.dsl, dòng 6, cột 18
Nhận được: Money + Distance
Gợi ý: Kiểm tra đơn vị của hai toán hạng.
```

## 12. Kiểm thử ngữ nghĩa toán tử

Toán tử là nền tảng của biểu thức nên cần được kiểm thử bằng các ví dụ có kết quả xác định.

### 12.1. Kiểm thử theo từng toán tử

Với mỗi toán tử, cần kiểm tra:

- Mọi kiểu toán hạng được hỗ trợ.
- Kết quả đúng và kiểu kết quả.
- Giá trị biên và giá trị đặc biệt.
- Trường hợp kiểu không tương thích.
- Hành vi với null hoặc unknown nếu có.
- Lỗi và thông báo lỗi.

### 12.2. Kiểm thử độ ưu tiên và tính kết hợp

Tạo các biểu thức có nhiều toán tử liền kề và so sánh kết quả với AST mong đợi. Ví dụ:

```text
2 + 3 * 4
(2 + 3) * 4
10 - 3 - 2
NOT A AND B
A OR B AND C
```

Các ví dụ này kiểm tra độ ưu tiên, dấu ngoặc và tính kết hợp.

### 12.3. Kiểm thử short-circuit

Đặt một hàm có thể phát sinh lỗi hoặc ghi nhận số lần được gọi ở vế phải:

```text
FALSE AND ham_co_loi()
TRUE OR ham_co_loi()
```

Nếu DSL định nghĩa short-circuit, hàm không được gọi trong hai trường hợp trên. Kiểm thử này xác nhận thứ tự đánh giá và tránh tác động phụ không mong muốn.

### 12.4. Kiểm thử kiểu miền và đơn vị

Thử các phép toán hợp lệ như `5 km + 300 m` nếu DSL hỗ trợ quy đổi, đồng thời thử phép toán không hợp lệ như `5 km + 2 kg`. Kiểm tra cả trường hợp cùng đơn vị, khác đơn vị và thiếu đơn vị.

### 12.5. Kiểm thử tính tương thích

Khi thay đổi độ ưu tiên hoặc nạp chồng toán tử, chạy lại bộ chương trình chuẩn cũ. Một thay đổi nhỏ về parser có thể làm AST khác và thay đổi kết quả của nhiều quy tắc.

## 13. Nguyên tắc thiết kế toán tử cho DSL

Một bộ toán tử tốt nên hỗ trợ cách suy nghĩ của người dùng miền và duy trì ngữ nghĩa nhất quán.

### 13.1. Chỉ cung cấp toán tử cần thiết

Không cần sao chép toàn bộ toán tử của một ngôn ngữ lập trình tổng quát. Nếu DSL chỉ mô tả chính sách, có thể không cần bitwise, con trỏ hoặc phép gán phức tạp.

### 13.2. Ưu tiên ý nghĩa rõ ràng

Toán tử nên có tên hoặc ký hiệu dễ hiểu với người dùng mục tiêu. Một từ khóa dài nhưng rõ có thể tốt hơn một ký hiệu ngắn nhưng dễ nhầm.

### 13.3. Giữ hợp đồng kiểu chặt chẽ

Chỉ cho phép phép toán có ý nghĩa trong miền. Kiểu `Money`, `Duration`, `Distance`, `DateTime` và `Status` nên có quy tắc riêng thay vì bị ép về kiểu số hoặc chuỗi chung.

### 13.4. Định nghĩa rõ thứ tự và giá trị biên

Độ ưu tiên, tính kết hợp, thứ tự đánh giá, short-circuit, null và lỗi phải có quy tắc thống nhất. Không để runtime tự chọn cách xử lý.

### 13.5. Tránh nạp chồng quá mức

Nạp chồng chỉ nên dùng khi các phép toán có quan hệ ý nghĩa dễ hiểu. Nếu thao tác khác bản chất, hãy dùng hàm hoặc từ khóa riêng.

### 13.6. Cân nhắc người dùng và môi trường nhập liệu

Nếu người dùng không chuyên lập trình, từ khóa như `AND`, `BEFORE` hoặc `WITHIN` có thể dễ hiểu hơn chuỗi ký hiệu. Nếu DSL được nhúng trong ngôn ngữ chủ, hãy tôn trọng giới hạn cú pháp của ngôn ngữ đó.

### 13.7. Duy trì tương thích khi thay đổi

Thêm toán tử mới thường ít rủi ro nếu không làm thay đổi cách phân tích biểu thức cũ. Đổi độ ưu tiên, tính kết hợp hoặc ý nghĩa của toán tử hiện có có thể là thay đổi phá vỡ tương thích. Nên có phiên bản ngôn ngữ và hướng dẫn chuyển đổi.

## 14. Ví dụ tổng hợp: toán tử trong DSL chính sách giao hàng

Giả sử DSL cần mô tả điều kiện miễn phí, khu vực áp dụng và giới hạn khối lượng.

```text
chinh_sach giao_hang_tieu_chuan {
    dieu_kien_mien_phi =
        tong_tien_sau_giam >= 500000 VND
        AND khach_hang.hang_thanh_vien IN {VANG, KIM_CUONG}

    dieu_kien_khu_vuc =
        dia_chi.khu_vuc WITHIN khu_vuc_noi_thanh
        OR dia_chi.khu_vuc IN khu_vuc_uu_tien

    dieu_kien_hop_le =
        khoi_luong > 0 kg
        AND khoi_luong <= 20 kg
        AND trang_thai_don_hang != DA_HUY

    phi_co_ban = 30000 VND
    phi_theo_km = khoang_cach * 5000 VND/km
}
```

Ví dụ này sử dụng nhiều nhóm toán tử:

- `>=`, `>`, `<=`, `!=` là toán tử so sánh.
- `AND`, `OR` là toán tử logic.
- `IN` kiểm tra thành viên của tập hợp.
- `WITHIN` là toán tử miền địa lý.
- `*` kết hợp khoảng cách với đơn giá để tạo ra giá trị tiền.
- `=` khai báo giá trị hoặc biểu thức theo cú pháp giả định của DSL.

Để chương trình có thể thực thi, đặc tả cần xác định `WITHIN` nhận kiểu vùng nào, `IN` so sánh mã hay đối tượng, phép nhân `Distance * Money/Distance` tạo kiểu `Money` ra sao và `=` là phép khai báo hay gán. Cũng cần xác định hai biểu thức logic được đánh giá như thế nào khi dữ liệu thành viên hoặc địa chỉ bị thiếu.

## 15. Những sai lầm thường gặp

### 15.1. Chỉ chọn ký hiệu mà không định nghĩa ngữ nghĩa

Việc có `+`, `-`, `AND` hay `IN` chưa đủ. Cần quy định kiểu toán hạng, kết quả, trường hợp biên và lỗi.

### 15.2. Không công bố độ ưu tiên

Người dùng có thể nhóm biểu thức khác với parser. Bảng độ ưu tiên và ví dụ cần nằm trong đặc tả.

### 15.3. Dùng một ký hiệu cho nhiều nghĩa khó đoán

Nạp chồng thiếu kiểm soát làm biểu thức khó hiểu. Chỉ dùng chung ký hiệu khi các phép toán có mối liên hệ tự nhiên.

### 15.4. Bỏ qua kiểu dữ liệu miền

Ép mọi giá trị thành số hoặc chuỗi làm mất thông tin về đơn vị và ý nghĩa. Kiểu miền giúp phát hiện phép toán sai ngay từ đầu.

### 15.5. Không xác định hành vi với null

Biểu thức chứa giá trị thiếu có thể cho kết quả bất ngờ. Cần chọn logic hai trạng thái, ba trạng thái hoặc chính sách báo lỗi và áp dụng nhất quán.

### 15.6. Để tác động phụ trong biểu thức logic

Short-circuit có thể khiến một toán hạng không được đánh giá. Hàm có tác động phụ trong biểu thức dễ tạo hành vi khó dự đoán; nên tách hành động khỏi điều kiện.

### 15.7. Thay đổi độ ưu tiên mà không xét chương trình cũ

Đổi bảng độ ưu tiên có thể thay đổi AST và kết quả. Cần xem đó là thay đổi ngữ nghĩa, kiểm thử tương thích và phiên bản hóa khi cần.

## 16. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Operator (toán tử) | Ký hiệu hoặc từ khóa biểu thị phép toán hay quan hệ |
| Operand (toán hạng) | Giá trị hoặc biểu thức mà toán tử tác động lên |
| Unary operator | Toán tử nhận một toán hạng |
| Binary operator | Toán tử nhận hai toán hạng |
| Ternary operator | Toán tử nhận ba thành phần |
| Prefix / Infix / Postfix | Toán tử đứng trước / giữa / sau toán hạng |
| Precedence | Độ ưu tiên giữa các toán tử |
| Associativity | Quy tắc kết hợp các toán tử cùng mức ưu tiên |
| Short-circuit evaluation | Đánh giá logic dừng sớm khi kết quả đã xác định |
| Operator overloading | Dùng cùng toán tử cho nhiều kiểu toán hạng với ngữ nghĩa được định nghĩa riêng |
| Type checking | Kiểm tra kiểu toán hạng và kiểu kết quả |
| Side effect | Tác động quan sát được ngoài giá trị trả về |
| Null / Unknown | Giá trị rỗng hoặc chưa xác định, tùy ngữ nghĩa DSL |
| Domain-specific operator | Toán tử biểu đạt một quan hệ hoặc phép toán chuyên biệt miền |

Toán tử là thành phần nhỏ nhưng có ảnh hưởng rộng đến cách người dùng đọc và viết DSL. Một bộ toán tử được thiết kế tốt cần có ký hiệu dễ hiểu, hợp đồng kiểu rõ, độ ưu tiên và thứ tự đánh giá nhất quán, đồng thời phản ánh đúng các phép toán có ý nghĩa trong miền. Khi đặc tả và kiểm thử đầy đủ những điểm này, biểu thức DSL sẽ dễ đọc, dễ dự đoán và được runtime thực hiện ổn định.

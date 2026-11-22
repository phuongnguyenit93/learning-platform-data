# Kiểm tra nối không mất mát và bảo toàn phụ thuộc sau phân rã

**Phân rã lược đồ (schema decomposition)** là việc thay một quan hệ lớn bằng nhiều quan hệ nhỏ hơn để hạn chế dữ liệu lặp và các bất thường khi thêm, sửa, xóa. Nhưng tách bảng không tự động làm mô hình tốt hơn: có những cách tách khiến phép JOIN tạo ra **bản ghi chưa từng tồn tại**, và có những cách tách làm mất khả năng **kiểm tra phụ thuộc hàm ngay trên từng bảng**.

Vì vậy, trước khi chốt một phân rã trong chương **Chuẩn hóa**, cần trả lời hai câu hỏi **độc lập**:

1. **Nối không mất mát (lossless-join decomposition):** từ các bảng sau phân rã, có khôi phục chính xác mọi quan hệ gốc hợp lệ bằng phép JOIN tự nhiên không?
2. **Bảo toàn phụ thuộc (dependency preservation):** các phụ thuộc hàm cần bảo vệ trong quan hệ gốc có thể được suy ra từ các phụ thuộc kiểm tra riêng trên từng bảng mới không?

Bài học thuộc module **DATABASE_DATA_MODELING**: chuyển yêu cầu nghiệp vụ thành mô hình quan hệ rõ ràng, với khóa, ràng buộc, phép kiểm chứng và quyết định thiết kế có thể bảo vệ được bằng lý luận lẫn dữ liệu thực tế. Các ví dụ dùng mô hình quan hệ hình thức và PostgreSQL để làm rõ sự khác nhau giữa **đúng về mặt lý thuyết** và **đúng trong vận hành hệ thống**.

## 1. Bài toán mở đầu: tách bảng rồi JOIN có chắc đúng?

Giả sử quan hệ ban đầu ghi một sinh viên học môn nào và giảng viên của môn đó:

| student_id | course_id | instructor_id |
| --- | --- | --- |
| S01 | C10 | I07 |
| S02 | C10 | I07 |
| S01 | C20 | I09 |

Nghiệp vụ quy định:

> Mỗi **course_id** có đúng một **instructor_id** phụ trách trong phạm vi dữ liệu đang xét.

Phụ thuộc hàm là **course_id → instructor_id**. Có thể tách quan hệ thành:

**StudentCourses(student_id, course_id)**

| student_id | course_id |
| --- | --- |
| S01 | C10 |
| S02 | C10 |
| S01 | C20 |

**CourseInstructors(course_id, instructor_id)**

| course_id | instructor_id |
| --- | --- |
| C10 | I07 |
| C20 | I09 |

JOIN hai bảng theo course_id khôi phục đúng ba bộ dữ liệu gốc. Đó là một **phân rã nối không mất mát**. Đồng thời, quy tắc course_id → instructor_id có thể được kiểm soát bằng một khóa duy nhất trên **CourseInstructors.course_id**; tức là phân rã này cũng **bảo toàn phụ thuộc**.

Tuy nhiên, hai kết luận ấy cần được chứng minh từ **quy tắc nghiệp vụ**, không chỉ vì một tập dữ liệu thử nghiệm có kết quả JOIN đúng. Một thiết kế có thể tình cờ JOIN đúng trên 100 hàng hôm nay nhưng sinh ra kết quả sai khi xuất hiện bản ghi hợp lệ mới vào ngày mai.

## 2. Ký hiệu và định nghĩa chính xác

Giả sử:

- **R(A, B, C, …)** là lược đồ quan hệ ban đầu với tập thuộc tính R.
- **F** là tập các **phụ thuộc hàm (functional dependencies, FD)** được nghiệp vụ xác nhận.
- **r** là một thể hiện dữ liệu bất kỳ của R thỏa tất cả FD trong F.
- **ρ = {R₁, R₂, …, Rₙ}** là tập các lược đồ con sau phân rã.
- **π_X(r)** là phép chiếu quan hệ r lên các thuộc tính trong X.
- **⋈** là phép nối tự nhiên theo những thuộc tính cùng tên.
- **F⁺** là tập tất cả phụ thuộc hàm suy ra từ F.
- **X⁺_F** là bao đóng thuộc tính X theo F.

Điều kiện nền là **R₁ ∪ R₂ ∪ … ∪ Rₙ = R**: mọi thuộc tính của lược đồ gốc vẫn xuất hiện ở ít nhất một lược đồ con. Nếu bỏ mất một thuộc tính mà nghiệp vụ còn cần, ta đã mất thông tin ngay ở cấp cấu trúc.

### 2.1. Nối không mất mát

Phân rã ρ là **nối không mất mát đối với F** khi, **với mọi** r thỏa F:

~~~text
r = π_R1(r) ⋈ π_R2(r) ⋈ ... ⋈ π_Rn(r)
~~~

Ý nghĩa: phân rã rồi nối lại trả đúng **tập bộ** ban đầu, không thêm bộ giả (*spurious tuples*) và không thiếu bộ nào.

Với phép JOIN tự nhiên trên các phép chiếu xuất phát từ **cùng một r** và xét ngữ nghĩa quan hệ tập hợp, phép JOIN luôn chứa các bộ gốc. Vì vậy, nguy cơ chính của phân rã sai là **sinh thêm các tổ hợp bộ giả**. Điều này khác với trường hợp các bảng vật lý bị cập nhật lệch nhau hoặc có NULL, khiến JOIN SQL trong hệ thống thực tế còn có thể bỏ sót hàng.

### 2.2. Bảo toàn phụ thuộc

Đặt **Fᵢ = π_Rᵢ(F)** là tập tất cả FD suy ra từ F mà chỉ sử dụng thuộc tính trong Rᵢ, nghĩa là:

~~~text
Fᵢ = { X → Y | X ∪ Y ⊆ Rᵢ và F ⊨ X → Y }
~~~

Phân rã là **bảo toàn phụ thuộc** nếu:

~~~text
(F₁ ∪ F₂ ∪ ... ∪ Fₙ)⁺ = F⁺
~~~

Một cách kiểm tra tương đương: **mọi FD trong tập F ban đầu đều suy ra được từ hợp các FD cục bộ**. Chiều ngược lại không gây khó khăn vì mỗi FD cục bộ vốn đã được suy ra từ F.

Điểm quan trọng: Fᵢ **không chỉ** gồm các FD được viết nguyên văn trong F và tình cờ nằm trọn trong Rᵢ. Nó còn chứa **những FD suy diễn được** nhờ tính bắc cầu, chẳng hạn A → C suy từ A → B và B → C.

Nếu một phụ thuộc **không được bảo toàn**, ta có thể vẫn áp nó bằng cơ chế JOIN/trigger/giao dịch trên nhiều bảng, nhưng **không thể chỉ dựa vào việc kiểm tra riêng các FD cục bộ**.

## 3. Công cụ nền: phụ thuộc hàm và bao đóng thuộc tính

Một phụ thuộc hàm **X → Y** phát biểu rằng: trong mọi thể hiện quan hệ hợp lệ, **hai bộ có cùng giá trị X phải có cùng giá trị Y**.

Nó là một quy tắc của miền nghiệp vụ, **không phải** một hiện tượng thống kê chỉ tình cờ đúng trong dữ liệu hiện tại.

Ví dụ:

~~~text
R(A, B, C)
F = { A → B, B → C }
~~~

Khi đó:

- **A⁺ = {A, B, C}**: từ A suy ra B, từ B suy ra C.
- **B⁺ = {B, C}**.
- **C⁺ = {C}**.
- **A** là khóa ứng viên của R nếu không có ràng buộc khác làm xuất hiện khóa tối thiểu khác.

### 3.1. Thuật toán tính bao đóng X⁺

~~~text
Input: tập thuộc tính X, tập phụ thuộc F
Result: X_plus

X_plus := X
repeat
    changed := false
    for each (LHS → RHS) in F:
        if LHS ⊆ X_plus and RHS ⊄ X_plus:
            X_plus := X_plus ∪ RHS
            changed := true
until changed = false

return X_plus
~~~

Để kiểm tra **F ⊨ X → Y**, tính X⁺ theo thuật toán trên; nếu **Y ⊆ X⁺** thì FD được suy ra.

Ví dụ với F = {A → B, B → C}: kiểm tra A → C bằng cách tính A⁺. Bước đầu có A; thêm B; tiếp đó thêm C. Vì C thuộc A⁺, kết luận A → C.

### 3.2. Ba lưu ý dễ sai

1. **Khóa ứng viên (candidate key)** là tập thuộc tính **tối thiểu** xác định toàn bộ R; một siêu khóa chứa thêm thuộc tính không nhất thiết là khóa ứng viên.
2. **FD có thể có vế trái nhiều thuộc tính**, ví dụ (student_id, course_id) → grade. Không được tự suy ra student_id → grade.
3. **FD không bảo đảm một hàng con luôn tồn tại.** Điều kiện “mỗi Order đã xác nhận có ít nhất một OrderLine” là ràng buộc số lượng, không phải một FD đơn giản.

## 4. Dấu hiệu JOIN bị mất mát: sinh bộ giả

Xét R(A, B, C) và **không có FD nào buộc B xác định A hoặc C**. Quan hệ gốc:

| A | B | C |
| --- | --- | --- |
| a1 | b1 | c1 |
| a2 | b1 | c2 |

Phân rã thành **R₁(A, B)** và **R₂(B, C)**:

**R₁**

| A | B |
| --- | --- |
| a1 | b1 |
| a2 | b1 |

**R₂**

| B | C |
| --- | --- |
| b1 | c1 |
| b1 | c2 |

JOIN tự nhiên trên B cho ra:

| A | B | C | Kết luận |
| --- | --- | --- | --- |
| a1 | b1 | c1 | Bộ gốc |
| a1 | b1 | c2 | **Bộ giả** |
| a2 | b1 | c1 | **Bộ giả** |
| a2 | b1 | c2 | Bộ gốc |

Vì cả hai hàng của R₁ đều mang B = b1, chúng nối được với **cả hai** hàng của R₂. Thông tin “A nào đi với C nào” đã bị xóa khỏi các bảng con.

Một truy vấn PostgreSQL minh họa:

~~~sql
WITH original(a, b, c) AS (
    VALUES
        ('a1', 'b1', 'c1'),
        ('a2', 'b1', 'c2')
),
r_ab AS (
    SELECT DISTINCT a, b FROM original
),
r_bc AS (
    SELECT DISTINCT b, c FROM original
),
reconstructed AS (
    SELECT r_ab.a, r_ab.b, r_bc.c
    FROM r_ab JOIN r_bc USING (b)
)
SELECT a, b, c
FROM reconstructed
EXCEPT
SELECT a, b, c
FROM original;
-- Hai bộ giả: (a1,b1,c2) và (a2,b1,c1).
~~~

Đây là **phân rã nối có mất mát (lossy-join)** dù **không xóa cột nào**: cả A, B, C vẫn xuất hiện ở các bảng. “Mất mát” ở đây là mất **liên hệ đúng giữa các giá trị**, dẫn đến dữ liệu giả khi nối lại.

**Đừng đánh đồng “nhiều hàng sau JOIN” với lỗi trong mọi tình huống.** Một phép JOIN một–nhiều đúng nghiệp vụ có thể tăng số hàng hợp lệ. Lỗi của phân rã là kết quả chứa **những bộ không thể được xác nhận từ quan hệ gốc hợp lệ**.

## 5. Tiêu chuẩn nối không mất mát cho phân rã nhị phân

Với phân rã R thành **R₁ và R₂**, và chỉ xét các ràng buộc FD thuộc F, có tiêu chuẩn cần và đủ:

~~~text
(R₁ ∩ R₂) → R₁    thuộc F⁺
          HOẶC
(R₁ ∩ R₂) → R₂    thuộc F⁺
~~~

Nói cách khác: **tập thuộc tính chung phải xác định được toàn bộ thuộc tính của ít nhất một trong hai quan hệ con**.

### 5.1. Cách kiểm tra bằng bao đóng

Đặt **X = R₁ ∩ R₂**.

1. Tính X⁺ từ **F của lược đồ gốc**.
2. Nếu **R₁ ⊆ X⁺** hoặc **R₂ ⊆ X⁺**, phân rã là **lossless** theo FD.
3. Nếu cả hai đều không phải tập con của X⁺, phân rã **không bảo đảm lossless** theo F.

Ví dụ:

~~~text
R(A,B,C), F = { A → B, B → C }
R₁(A,B), R₂(B,C)

X = R₁ ∩ R₂ = {B}
B⁺ = {B,C}
R₂ = {B,C} ⊆ B⁺
⇒ Nối không mất mát.
~~~

B là thuộc tính chung; nhờ **B → C**, mỗi giá trị B chỉ kết hợp với **một** giá trị C hợp lệ. Vì vậy khi nối AB với BC, không thể ghép A với C tùy tiện.

### 5.2. Vì sao tiêu chuẩn đúng? Trực giác chứng minh

Mỗi bộ của kết quả JOIN được ghép từ một bộ trong π_R₁(r) và một bộ trong π_R₂(r), đồng ý trên X = R₁ ∩ R₂.

Nếu X → R₂, mọi bộ gốc có cùng X phải có cùng toàn bộ phần R₂. Vì vậy bộ R₂ được ghép không thể mang những thuộc tính riêng R₂ khác với bộ R₂ của chính bộ gốc đã sinh ra phần R₁. Bộ kết quả phải là bộ đã tồn tại trong r.

Lập luận đối xứng nếu X → R₁. Nếu không có phụ thuộc nào như vậy, có thể tồn tại một thể hiện thỏa F nhưng phép chiếu rồi nối tạo ra bộ giả.

### 5.3. Tiêu chuẩn này có phạm vi áp dụng

Tiêu chuẩn trên là **cần và đủ khi F chỉ là tập phụ thuộc hàm**. Nếu còn các ràng buộc mạnh hơn như **phụ thuộc đa trị (MVD)**, một phân rã có thể nối không mất mát nhờ MVD dù không có FD xác định một phía.

Ví dụ với R(A, B, C) và **A ↠ B**, mô hình cho phép mọi kết hợp B–C trong cùng một A, nên phân rã thành AB và AC là lossless theo MVD. Không được dùng kết luận “không lossless theo FD” để phủ nhận một ràng buộc MVD đã được chứng minh.

Ngoài ra, tiêu chuẩn nhị phân **không được áp máy móc** cho ba bảng trở lên chỉ bằng cách kiểm tra từng cặp bất kỳ. Với phân rã nhiều quan hệ, cần một phép chứng minh toàn cục, một chuỗi ghép lossless hợp lệ hoặc thuật toán **chase**.

## 6. Lossless không đồng nghĩa bảo toàn phụ thuộc

Dùng lại:

~~~text
R(A,B,C)
F = { A → B, B → C }
~~~

Xét hai phân rã khác nhau.

### 6.1. Phân rã tốt: AB và BC

~~~text
R₁(A,B), R₂(B,C)
~~~

- **Lossless:** giao là B; B → BC vì B → C.
- **Preserving:** R₁ bảo vệ A → B, R₂ bảo vệ B → C.
- A → C suy theo tính bắc cầu từ hai phụ thuộc cục bộ.
- Có thể dùng UNIQUE/PK trên A của bảng AB và B của bảng BC.

Đây là ví dụ **cả hai tính chất đều đạt**.

### 6.2. Phân rã lossless nhưng không bảo toàn FD: AB và AC

~~~text
R₁(A,B), R₂(A,C)
~~~

- **Lossless:** giao là A; A → AB và A → AC (vì A → B → C).
- **FD cục bộ ở AB:** A → B.
- **FD cục bộ ở AC:** A → C.
- **FD gốc B → C:** không suy được từ chỉ {A → B, A → C}.

Chứng minh phần cuối bằng bao đóng:

~~~text
G = { A → B, A → C }
B⁺_G = {B}
C ∉ B⁺_G
⇒ G không suy ra B → C.
~~~

Có thể có dữ liệu **đều hợp lệ trong từng bảng con**:

**AB**

| A | B |
| --- | --- |
| a1 | b1 |
| a2 | b1 |

**AC**

| A | C |
| --- | --- |
| a1 | c1 |
| a2 | c2 |

Khi JOIN theo A, ta nhận đúng hai bộ, không có tổ hợp giả:

~~~text
(a1, b1, c1)
(a2, b1, c2)
~~~

Nhưng hai bộ này **vi phạm B → C**: cùng B = b1 mà C khác nhau.

Đây là khác biệt cốt lõi:

- **Lossless** khẳng định: *nếu các bảng con được chiếu từ một quan hệ gốc hợp lệ*, nối lại sẽ không tự sinh thêm bộ.
- **Preserving** khẳng định: *khi thao tác trực tiếp trên từng bảng con*, kiểm tra FD nội bộ đủ để ngăn những trạng thái vi phạm FD gốc.

Một phân rã có thể khôi phục chính xác các dữ liệu **hợp lệ ban đầu** nhưng vẫn cho phép tạo ra những trạng thái vật lý **mới, không hợp lệ theo nghiệp vụ** nếu không bổ sung ràng buộc xuyên bảng.

### 6.3. Ngược lại: bảo toàn phụ thuộc nhưng JOIN có mất mát

Đổi giả định thành:

~~~text
R(A,B,C)
F = { A → B }
R₁(A,B), R₂(B,C)
~~~

A → B được bảo vệ trọn vẹn trong R₁, nên **phụ thuộc đã cho được bảo toàn**. Nhưng:

~~~text
R₁ ∩ R₂ = {B}
B⁺_F = {B}
B không xác định A hoặc C
⇒ Không lossless.
~~~

Hai bộ (a1,b1,c1) và (a2,b1,c2) đều thỏa A → B, nhưng nối AB và BC vẫn tạo hai bộ giả như phần 4.

**Kết luận:** bảo toàn FD **không kéo theo** nối không mất mát; nối không mất mát **không kéo theo** bảo toàn FD.

## 7. Kiểm tra bảo toàn phụ thuộc một cách hệ thống

Cho phân rã ρ = {R₁,…,Rₙ}.

### 7.1. Bước 1: liệt kê FD nghiệp vụ và giảm phủ

Từ yêu cầu nghiệp vụ, ghi F rõ ràng; có thể dùng **phủ tối thiểu/canonical cover** để giảm số phụ thuộc cần xét:

- Tách các FD có vế phải nhiều thuộc tính thành các FD vế phải một thuộc tính.
- Bỏ thuộc tính thừa ở vế trái khi việc bỏ vẫn giữ tập hệ quả.
- Bỏ FD dư thừa khi tập còn lại vẫn suy ra nó.

Phủ tối thiểu giúp kiểm tra dễ hơn nhưng **không thay đổi F⁺**. Không nên “rút gọn” bằng cách bỏ FD chỉ vì nó hiếm khi bị vi phạm trong dữ liệu mẫu.

### 7.2. Bước 2: tìm các FD chiếu xuống từng bảng

Với Rᵢ, chỉ những phụ thuộc có **cả vế trái và vế phải** nằm trong Rᵢ mới là FD cục bộ có thể kiểm tra chỉ từ bảng đó.

Quan trọng: phải xét FD **suy diễn**. Với F = {A → B, B → C}:

~~~text
π_AB(F) chứa A → B
π_AC(F) chứa A → C   (dù A → C không viết trực tiếp trong F)
π_BC(F) chứa B → C
~~~

Việc tính toàn bộ phép chiếu FD có thể tốn kém khi có nhiều thuộc tính; trong hệ thống thực tế thường dùng thuật toán kiểm tra bảo toàn trực tiếp thay vì liệt kê tất cả FD có thể suy ra.

### 7.3. Bước 3: kiểm tra từng FD của F

Gọi **G = F₁ ∪ F₂ ∪ … ∪ Fₙ**. Với mỗi **X → Y** trong F, tính X⁺ theo G. Nếu mọi lần đều có **Y ⊆ X⁺_G**, tất cả FD được bảo toàn.

Bảng ví dụ:

| F gốc | Phân rã | FD kiểm tra tại bảng con | Kết luận |
| --- | --- | --- | --- |
| A → B, B → C | AB, BC | A → B trong AB; B → C trong BC | **Bảo toàn** |
| A → B, B → C | AB, AC | A → B trong AB; A → C trong AC | **Không bảo toàn B → C** |
| A → B | AB, BC | A → B trong AB | **Bảo toàn** nhưng có thể lossy |

### 7.4. Thuật toán kiểm tra trực tiếp không cần liệt kê toàn bộ Fᵢ

Để kiểm tra xem **X → Y** có được bảo toàn hay không, ta có thể lặp bằng các phép bao đóng theo F gốc:

~~~text
Z := X
repeat
    old_Z := Z
    for each relation Rᵢ:
        T := (Z ∩ Rᵢ)⁺_F ∩ Rᵢ
        Z := Z ∪ T
until Z = old_Z

return (Y ⊆ Z)
~~~

Giải thích: tại mỗi bảng Rᵢ, chỉ có thể dùng những thuộc tính **đã biết và nằm trong bảng ấy** để suy ra thêm những thuộc tính **cũng nằm trong bảng ấy**. Lặp cho đến khi không thể suy ra thêm gì.

Nếu thuật toán trả về TRUE cho mọi FD trong một phủ tương đương của F, phân rã bảo toàn F. Nếu một FD không đạt, cần áp nó bằng ràng buộc xuyên bảng hoặc thay thiết kế.

Ví dụ **AB + AC** với F = {A → B, B → C}, kiểm tra **B → C**:

~~~text
Z = {B}
R_AB: (Z ∩ AB) = {B}; B⁺_F ∩ AB = {B}
R_AC: (Z ∩ AC) = ∅; không bổ sung thuộc tính
Điểm cố định Z = {B}; thiếu C.
⇒ B → C không được bảo toàn.
~~~

Ví dụ **AB + BC**, cùng FD:

~~~text
Z = {B}
R_BC: B⁺_F ∩ BC = {B,C}
Điểm cố định chứa C.
⇒ B → C được bảo toàn.
~~~

Thuật toán này xét khả năng **suy diễn qua các phụ thuộc cục bộ**, không phải cố chứng minh mọi ràng buộc nghiệp vụ chỉ bằng một bảng. Các quy tắc tổng hợp số tiền, tồn tại ít nhất một hàng con hoặc phân quyền theo trạng thái có thể không phải FD.

## 8. Thuật toán chase để kiểm tra lossless join

Khi có **hơn hai** lược đồ con, hoặc muốn một phép kiểm chứng có hệ thống, có thể dùng **chase tableau** dưới tập phụ thuộc hàm.

### 8.1. Ý tưởng

Tạo một bảng ký hiệu:

- Có **một hàng** cho mỗi quan hệ con Rᵢ.
- Có **một cột** cho mỗi thuộc tính Aⱼ của R.
- Nếu thuộc tính Aⱼ **có mặt** trong Rᵢ, ghi ký hiệu chung **aⱼ**.
- Nếu thuộc tính Aⱼ **không có mặt**, ghi ký hiệu riêng **bᵢⱼ** (khác mọi ký hiệu b khác).
- Với mỗi FD X → Y, nếu hai hàng có ký hiệu **giống nhau trên X**, ép các ký hiệu trên Y bằng nhau.
- Khi hợp nhất ký hiệu, nếu một trong chúng là **aⱼ** thì ưu tiên thay bằng aⱼ; các ô tương ứng đã hợp nhất phải giữ cùng giá trị.
- Lặp cho đến khi không đổi. Nếu có **một hàng toàn bộ là ký hiệu a theo cột**, phân rã **lossless đối với các FD**.

Trong chase trên FD, việc có hàng toàn a là tiêu chí thành công; nếu quá trình dừng mà không có hàng toàn a, phép phân rã không được bảo đảm lossless theo tập FD đã cho.

### 8.2. Ví dụ từng bước: R(A,B,C) → AB, BC

Cho **F = {A → B, B → C}**. Khởi tạo:

| Hàng | A | B | C |
| --- | --- | --- | --- |
| R_AB | a_A | a_B | b_1C |
| R_BC | b_2A | a_B | a_C |

Hai hàng có cùng **a_B** ở cột B. Vì **B → C**, bắt buộc giá trị C của chúng bằng nhau, nên thay **b_1C** bằng **a_C**:

| Hàng | A | B | C |
| --- | --- | --- | --- |
| R_AB | **a_A** | **a_B** | **a_C** |
| R_BC | b_2A | a_B | a_C |

Hàng R_AB đã toàn ký hiệu a ⇒ phân rã **nối không mất mát**.

### 8.3. Nếu không có FD đủ mạnh?

Với R(A,B,C) → AB,BC và F rỗng, không có bước chase nào làm thay đổi bảng ban đầu. Không có hàng toàn a ⇒ phân rã **không lossless** dưới các FD đã biết, khớp với ví dụ sinh bộ giả.

### 8.4. Những giới hạn cần nhớ

- Chase ở đây dùng **phụ thuộc hàm**; nếu xét thêm MVD, join dependency hay ràng buộc tổng quát khác thì thuật toán, quy tắc chase và giả thiết thay đổi.
- Nếu có thể chứng minh chuỗi ghép **từng bước** đều lossless theo các phụ thuộc liên quan, đó là một chứng minh đủ tốt cho phân rã nhiều bảng; không nhất thiết phải lập tableau.
- Không được kiểm tra độc lập từng cặp bảng bất kỳ rồi suy ra ngay toàn bộ phép nối nhiều bảng là đúng.
- Việc đếm các hàng JOIN trên dữ liệu thực tế không thay cho chứng minh **với mọi thể hiện hợp lệ**.

## 9. Bảo toàn phụ thuộc khi chọn giữa 3NF và BCNF

Chuẩn hóa thường hướng đến **3NF** hoặc **BCNF** để giảm bất thường cập nhật. Tuy nhiên, **BCNF không phải lúc nào cũng bảo toàn tất cả FD khi phân rã**, dù vẫn có thể đạt lossless.

### 9.1. Phân rã BCNF lossless nhưng mất một phụ thuộc

Xét:

~~~text
R(A,B,C)
F = { AB → C, C → B }
~~~

Xác định khóa:

- **(AB)⁺ = ABC** ⇒ AB là khóa ứng viên.
- **(AC)⁺ = ABC** nhờ C → B ⇒ AC cũng là khóa ứng viên.
- A, B, C đều là **thuộc tính khóa (prime attributes)** vì mỗi thuộc tính nằm trong ít nhất một khóa ứng viên.

FD **C → B** vi phạm BCNF vì **C không phải siêu khóa** của R. Một cách phân rã theo C → B là:

~~~text
R₁(C,B)
R₂(A,C)
~~~

**Lossless:**

~~~text
R₁ ∩ R₂ = {C}
C → B ⇒ C → CB = R₁
⇒ Nối không mất mát.
~~~

**Không bảo toàn phụ thuộc AB → C:**

- R₁ có **C → B**.
- R₂ không có FD không tầm thường bắt buộc nào giữa A và C theo F đã cho.
- Chỉ từ các ràng buộc cục bộ trên CB và AC, không suy ra **AB → C**.

Có thể nhập dữ liệu:

**CB**

| C | B |
| --- | --- |
| c1 | b1 |
| c2 | b1 |

**AC**

| A | C |
| --- | --- |
| a1 | c1 |
| a1 | c2 |

JOIN theo C sinh:

~~~text
(a1, b1, c1)
(a1, b1, c2)
~~~

Cả hai bảng con đều có thể thỏa FD cục bộ, nhưng cùng **AB = (a1,b1)** lại có hai C khác nhau ⇒ **vi phạm AB → C**. Muốn cưỡng chế FD đó trên lược đồ đã phân rã phải dùng cơ chế phối hợp nhiều bảng hoặc chọn thiết kế khác.

**Lưu ý:** R gốc trong ví dụ đã thỏa **3NF**, vì B là thuộc tính khóa (prime). Vì vậy một lựa chọn hợp lệ là **giữ R ở 3NF** để bảo toàn phụ thuộc, thay vì ép phân rã BCNF làm việc kiểm soát AB → C khó hơn.

### 9.2. Vì sao 3NF thường là điểm cân bằng?

Có một thuật toán **tổng hợp lược đồ 3NF (3NF synthesis)** dựa trên phủ tối thiểu của F, tạo quan hệ cho các FD và thêm quan hệ chứa một khóa ứng viên khi cần. Khi thực hiện đúng, thuật toán bảo đảm:

- **Nối không mất mát**.
- **Bảo toàn các phụ thuộc hàm**.
- Mỗi quan hệ tạo ra đạt **3NF**.

Một số bước điển hình:

1. Tính phủ tối thiểu/canonical cover của F.
2. Với mỗi FD dạng X → A (hoặc nhóm cùng vế trái), tạo quan hệ gồm X ∪ {A}.
3. Loại quan hệ bị bao hoàn toàn trong một quan hệ đã tạo khác nếu không làm đổi yêu cầu thiết kế.
4. Nếu chưa có quan hệ nào chứa **một khóa ứng viên của R gốc**, thêm quan hệ chứa khóa đó.
5. Kiểm tra lại lossless và preservation; chọn PK/FK, các quy tắc nghiệp vụ liên quan.

Ví dụ:

~~~text
R(A,B,C,D)
F = { A → B, B → C, C → D }
~~~

Phân rã 3NF tự nhiên:

~~~text
R_AB(A,B)
R_BC(B,C)
R_CD(C,D)
~~~

- **Bảo toàn:** mỗi FD gốc nằm nguyên trong một bảng con.
- **Lossless:** AB ⋈ BC lossless vì B → BC; sau đó nối với CD theo C, và C → CD.
- Mỗi bảng con có khóa tại thuộc tính ở vế trái FD của nó.
- A là khóa ứng viên của R gốc và có mặt trong R_AB, nên không phải thêm một bảng chỉ chứa khóa.

Ví dụ này cũng có thể đạt BCNF. Vấn đề đánh đổi chỉ xuất hiện ở **những tập FD nhất định**, không phải mọi lần phân rã BCNF đều mất phụ thuộc.

### 9.3. Cách ra quyết định

Nếu BCNF làm mất một FD nghiệp vụ quan trọng mà không thể cưỡng chế rẻ và tin cậy bằng các bảng riêng, **3NF có thể là lựa chọn đúng hơn**. Ngược lại, nếu nguy cơ lặp dữ liệu lớn và phụ thuộc mất đi đã được quản lý an toàn bằng cơ chế riêng, phân rã BCNF vẫn đáng cân nhắc.

**Không nên chọn chuẩn chỉ vì tên mức chuẩn “cao hơn”.** Cần xét tổng chi phí duy trì tính đúng đắn, thay đổi nghiệp vụ, truy vấn và giao dịch.

## 10. Hiện thực trong PostgreSQL: minh họa các FD có thể kiểm soát

### 10.1. Phân rã lossless và bảo toàn FD

Với R(StudentID, CourseID, InstructorID) và FD CourseID → InstructorID:

~~~sql
CREATE TABLE course_instructors (
    course_id BIGINT PRIMARY KEY,
    instructor_id BIGINT NOT NULL
);

CREATE TABLE student_courses (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL
        REFERENCES course_instructors(course_id)
        ON DELETE RESTRICT,
    PRIMARY KEY (student_id, course_id)
);

-- Dữ liệu mẫu:
INSERT INTO course_instructors (course_id, instructor_id)
VALUES (10, 7), (20, 9);

INSERT INTO student_courses (student_id, course_id)
VALUES (1, 10), (2, 10), (1, 20);

-- Khôi phục quan hệ ở mức ba thuộc tính:
SELECT sc.student_id, sc.course_id, ci.instructor_id
FROM student_courses AS sc
JOIN course_instructors AS ci USING (course_id)
ORDER BY sc.student_id, sc.course_id;
~~~

**course_id PRIMARY KEY** trong course_instructors bảo vệ CourseID → InstructorID. Khóa ngoại ở student_courses bảo vệ rằng mỗi môn sinh viên học **có hàng CourseInstructor tương ứng**, tránh mất hàng trong phép JOIN vật lý do tham chiếu mồ côi. Khóa ghép ở student_courses ngăn một cặp sinh viên–môn học bị lặp.

Các lựa chọn này minh họa **ràng buộc của lược đồ vật lý**, bổ sung cho phép chứng minh lossless hình thức. Phép chứng minh lossless giả định các bảng con thực sự là **phép chiếu của cùng một quan hệ gốc hợp lệ**; một hệ thống tự ghi hai bảng độc lập còn cần PK, FK, giao dịch và quy tắc cập nhật để duy trì tính nhất quán đó.

Nếu nghiệp vụ đổi thành một môn có thể có nhiều giảng viên theo học kỳ hoặc lớp, FD **CourseID → InstructorID** không còn đúng. Phải thiết kế lại phụ thuộc, ví dụ **(CourseID, TermID, SectionID) → InstructorID** nếu chính sách mới phù hợp, chứ không giữ khóa cũ rồi ép dữ liệu sai.

### 10.2. Lossless nhưng thiếu bảo toàn FD trong SQL

Với R(A,B,C), F = {A → B, B → C}, phân rã AB và AC có thể tạo:

~~~sql
CREATE TABLE demo_ab (
    a TEXT PRIMARY KEY,
    b TEXT NOT NULL
);

CREATE TABLE demo_ac (
    a TEXT PRIMARY KEY REFERENCES demo_ab(a),
    c TEXT NOT NULL
);

INSERT INTO demo_ab (a,b)
VALUES ('a1','b1'), ('a2','b1');

INSERT INTO demo_ac (a,c)
VALUES ('a1','c1'), ('a2','c2');

SELECT ab.a, ab.b, ac.c
FROM demo_ab AS ab
JOIN demo_ac AS ac USING (a)
ORDER BY ab.a;
~~~

Cả hai bảng đều hợp lệ theo khóa và FK:

- **A → B** được bảo vệ bởi PK A của demo_ab.
- **A → C** được bảo vệ bởi PK A của demo_ac.
- Nhưng **B → C không được bảo vệ**.

Kết quả JOIN có hai hàng cùng B = b1 nhưng C khác nhau. **Không có một FK nào trong ví dụ được dùng để kiểm soát phụ thuộc B → C**, bởi B và C không cùng nằm trong một bảng với UNIQUE/FD tương ứng. Đây là ví dụ thực tế của **phụ thuộc không được bảo toàn**.

Nếu B → C là luật nghiệp vụ bắt buộc, một thiết kế tốt hơn có thể dùng:

~~~sql
CREATE TABLE demo_bc (
    b TEXT PRIMARY KEY,
    c TEXT NOT NULL
);

CREATE TABLE demo_ab_preserving (
    a TEXT PRIMARY KEY,
    b TEXT NOT NULL REFERENCES demo_bc(b)
);
~~~

B → C được bảo vệ bởi PK của demo_bc; A → B bởi PK của demo_ab_preserving; phân rã AB,BC cũng lossless do B → BC.

### 10.3. Ngay cả FD có thể bảo toàn vẫn cần triển khai constraint

“Bảo toàn phụ thuộc” là **tính chất của phân rã lược đồ**, không có nghĩa hệ quản trị tự sinh UNIQUE/FK hoặc tự biết các FD nghiệp vụ. Nếu một phụ thuộc cục bộ X → Y cần được bảo vệ, phải thiết kế khóa, UNIQUE, trigger hoặc phương án kiểm tra phù hợp.

Một FD như **CourseID → InstructorID** có thể dễ hiện thực bằng một khóa trên CourseID. Nhưng một FD phức tạp trên bảng với nhiều hàng và ngoại lệ trạng thái có thể cần mô hình bổ sung. Không nên đồng nhất toàn bộ FD toán học với khả năng diễn đạt trực tiếp bằng một lệnh UNIQUE.

## 11. Kiểm chứng trên dữ liệu mẫu: hữu ích nhưng không thay chứng minh

Với một bảng dữ liệu nguồn thực tế, có thể so sánh **quan hệ gốc** và **kết quả nối các phép chiếu**.

Giả sử tồn tại bảng **enrollment_source(student_id, course_id, instructor_id)**, với các cột không NULL và chỉ lưu những bộ phân biệt. Truy vấn:

~~~sql
WITH student_course AS (
    SELECT DISTINCT student_id, course_id
    FROM enrollment_source
),
course_instructor AS (
    SELECT DISTINCT course_id, instructor_id
    FROM enrollment_source
),
rebuilt AS (
    SELECT sc.student_id, sc.course_id, ci.instructor_id
    FROM student_course AS sc
    JOIN course_instructor AS ci USING (course_id)
),
spurious AS (
    SELECT student_id, course_id, instructor_id FROM rebuilt
    EXCEPT
    SELECT student_id, course_id, instructor_id FROM enrollment_source
),
missing AS (
    SELECT student_id, course_id, instructor_id FROM enrollment_source
    EXCEPT
    SELECT student_id, course_id, instructor_id FROM rebuilt
)
SELECT
    (SELECT COUNT(*) FROM spurious) AS spurious_count,
    (SELECT COUNT(*) FROM missing) AS missing_count;
~~~

Nếu cả hai số đếm bằng **0**, phép JOIN đang khôi phục đúng **tập bộ trên dataset được kiểm tra**. Nhưng việc đó **không chứng minh phân rã lossless với mọi dữ liệu hợp lệ trong tương lai**. Cần một lập luận theo FD hoặc ràng buộc nghiệp vụ.

Để phát hiện một FD bị vi phạm trong dữ liệu hiện có, chẳng hạn **CourseID → InstructorID** (các cột không NULL):

~~~sql
SELECT course_id
FROM enrollment_source
GROUP BY course_id
HAVING COUNT(DISTINCT instructor_id) > 1;
~~~

Truy vấn trả không hàng chỉ nói rằng **chưa thấy vi phạm trong dữ liệu đã khảo sát**. Nó không thay thế việc xác nhận FD từ nghiệp vụ. Khi có NULL hoặc ngữ nghĩa giá trị thiếu, COUNT(DISTINCT ...) có thể không phản ánh hết những trường hợp cần xem xét.

### Một khác biệt giữa đại số quan hệ và SQL

Định nghĩa lossless dựa trên **ngữ nghĩa tập hợp**: mỗi bộ xuất hiện một lần. SQL mặc định có thể giữ **bản sao trùng** (bag/multiset), và JOIN có thể nhân số dòng khi khóa không duy nhất. Vì vậy ví dụ kiểm thử dùng **DISTINCT** và **EXCEPT** để đối chiếu tập bộ.

Ngoài ra, trong SQL, so sánh JOIN thông thường **không coi NULL = NULL là TRUE**. Lý thuyết FD và phép nối tự nhiên trong mô hình quan hệ cổ điển không giả định NULL theo ngữ nghĩa ba giá trị của SQL. Do đó phải xác định riêng chính sách NULL/NOT NULL, khóa và tính hiện diện tham chiếu khi chuyển từ chứng minh lý thuyết sang dữ liệu thật.

## 12. Vấn đề cập nhật: tại sao dependency preservation đáng giá?

Một FD có thể được bảo vệ trong một bảng bằng PK/UNIQUE thích hợp, nhưng nếu các thuộc tính xác định và bị xác định nằm ở **nhiều bảng khác nhau**, việc kiểm tra mỗi hàng mới có thể cần một phép JOIN hoặc quy trình giao dịch xuyên bảng.

### 12.1. Tình huống không bảo toàn B → C

Trong phân rã AB + AC, để thêm một bộ với A mới, ứng dụng phải kiểm tra xem:

- B đã xuất hiện trong AB chưa;
- nếu B đã xuất hiện, tất cả những A đang gắn với B có giá trị C tương ứng trong AC hay không;
- C của bộ mới có trùng với C bắt buộc theo B không.

Đó là kiểm tra **B → C qua JOIN**, không chỉ trên một bảng. Hai giao dịch đồng thời có thể cùng thấy chưa có B rồi thêm hai A khác nhau với cùng B nhưng C khác nhau, nếu không có khóa hoặc ràng buộc phù hợp.

**Không bảo toàn FD không tự chứng minh dữ liệu sẽ hỏng**, nhưng làm việc bảo đảm dữ liệu đúng **tốn hơn và dễ bỏ sót** nếu triển khai không đầy đủ.

### 12.2. Thiết kế lại thay vì vá lỗi sau JOIN

Nếu B → C là bất biến thật sự, đưa cặp **(B,C)** vào một bảng nơi B là khóa thường rõ ràng hơn:

~~~text
BC(B PRIMARY KEY, C)
AB(A PRIMARY KEY, B FOREIGN KEY REFERENCES BC)
~~~

Như vậy:

- Không thể tồn tại hai C khác nhau cho một B.
- Thao tác tạo A mới phải tham chiếu B tồn tại.
- Có thể cập nhật quy tắc liên quan B/C ở một nơi thay vì nhiều hàng A.

Tuy nhiên, không phải mọi quy tắc xuyên bảng đều là FD hoặc đều có thể đưa về một UNIQUE. Ví dụ “mỗi đơn CONFIRMED có ít nhất một dòng” là ràng buộc tồn tại; “tổng giá các dòng bằng số tiền hóa đơn” là ràng buộc tổng hợp. Dependency preservation không thay thế thiết kế các bất biến đó.

## 13. Đánh đổi giữa chuẩn hóa, hiệu năng và ràng buộc

Một phân rã có thể đạt cả lossless và preservation nhưng vẫn yêu cầu nhiều JOIN để phục vụ truy vấn; ngược lại, một bảng rộng có thể tránh JOIN nhưng lặp lại thông tin và gây bất thường cập nhật.

| Khía cạnh | Câu hỏi thiết kế |
| --- | --- |
| Nối không mất mát | Các bảng mới có khôi phục chính xác **quan hệ gốc hợp lệ** không? |
| Bảo toàn FD | Mọi FD quan trọng có thể được kiểm tra từ **các bảng riêng**, không cần JOIN kiểm tra hay không? |
| Chuẩn hóa | Mỗi bảng đang ở 3NF hay BCNF? Có dữ liệu lặp gây bất thường sửa/xóa không? |
| Khóa và tham chiếu | Khóa ứng viên, UNIQUE, PK, FK có thực thi được các FD và quan hệ không? |
| Truy vấn | Các JOIN bổ sung có chấp nhận được với khối lượng dữ liệu và SLA không? |
| Giao dịch | Thêm/sửa/xóa cùng một thực thể có cần ghi nhiều bảng nguyên tử không? |
| Lịch sử | FD có thay đổi theo thời gian, phiên bản hoặc phạm vi tenant không? |
| Tiến hóa | Khi xuất hiện một loại đối tượng, trạng thái hoặc quy tắc mới, việc sửa lược đồ có phá FD cũ không? |

### 13.1. FD theo ngữ cảnh và thời gian

Phát biểu “CourseID → InstructorID” có thể đúng **trong một học kỳ** nhưng sai nếu nhìn qua nhiều học kỳ. Khi đó FD đúng hơn có thể là:

~~~text
(CourseID, TermID) → InstructorID
~~~

Nếu một môn có nhiều lớp học phần, có thể cần thêm **SectionID**. Phân rã dựa trên FD sai sẽ tạo ràng buộc quá chặt hoặc lược đồ không biểu diễn được dữ liệu thật.

Tương tự, trong hệ thống đa tenant:

~~~text
(TenantID, ExternalCustomerCode) → CustomerID
~~~

khác hoàn toàn với **ExternalCustomerCode → CustomerID** trên toàn hệ thống. Khóa và các phép chiếu phải giữ đúng phạm vi, nếu không có thể nối nhầm bản ghi giữa các tenant.

### 13.2. Denormalization và các cấu trúc dẫn xuất

Trong hệ thống báo cáo, có thể cố tình lưu bảng tổng hợp, dimension hoặc bản chụp đã phi chuẩn hóa để tăng tốc đọc. Nhưng việc lưu nhiều biểu diễn của cùng một sự thật đặt thêm câu hỏi:

- Bảng nào là **nguồn sự thật**?
- Khi dữ liệu nguồn đổi, bảng dẫn xuất được cập nhật **đồng bộ hay bất đồng bộ**?
- Khoảng trễ cho phép là bao nhiêu?
- Kiểm tra nào xác nhận dữ liệu dẫn xuất không mâu thuẫn với ràng buộc gốc?
- Nếu JOIN làm nhân bản số liệu, có xác định đúng **mức hạt (grain)** của fact không?

Việc denormalize **không thay đổi** định nghĩa lossless/preservation, nhưng làm phát sinh các bất biến nhất quán giữa bản gốc và bản dẫn xuất.

## 14. Liên hệ với document, graph và mô hình phân tích

Hai tiêu chí đang xét xuất phát từ lý thuyết quan hệ và phụ thuộc hàm. Trong công nghệ khác, ta vẫn cần bảo vệ **khả năng tái tạo thông tin** và **các quy tắc nhất quán**, nhưng không nên coi mọi cách biểu diễn đều là một phép phân rã quan hệ theo cùng công thức.

| Mô hình lưu trữ | Điều tương ứng với tính khôi phục | Điều tương ứng với bảo vệ quy tắc |
| --- | --- | --- |
| **Quan hệ** | JOIN các phép chiếu không sinh bộ giả | FD cục bộ suy ra toàn bộ FD gốc |
| **Document** | Tách/nhúng dữ liệu mà vẫn giữ đúng ID và liên hệ giữa các object | Schema validation, quy tắc nhất quán xuyên document, kiểm soát cập nhật đồng thời |
| **Graph** | Khi tách node/cạnh, vẫn giữ đúng loại, hướng và định danh cạnh | Kiểm soát loại cạnh, tính duy nhất, bội số, ràng buộc theo đường đi |
| **Phân tích/warehouse** | JOIN fact–dimension/bridge không làm tăng hoặc mất sự kiện ngoài chủ đích | Khóa, grain, lịch sử dimension và quy tắc tính chỉ tiêu |

### Document: tách các mảng song song dễ mất liên hệ

Giả sử một đơn có hai dòng hàng, mỗi dòng mang **productId** và **unitPrice**. Nếu tách thành hai mảng độc lập productIds và prices mà không giữ khóa xác định từng dòng, phép ghép lại có thể gán giá cho nhầm sản phẩm. Đó là một vấn đề tương tự với **mất tương quan khi phân rã**.

Cách an toàn hơn thường là lưu **mỗi dòng thành một object đầy đủ**, hoặc dùng một định danh dòng để liên kết các collection đã tách. Quy tắc thuộc tính và giao dịch vẫn cần được bảo vệ.

### Graph: nhiều đường không có nghĩa nhiều sự kiện

Nếu một nút Category có nhiều cha, có thể có nhiều đường từ sản phẩm đến cùng một nhóm tổ tiên. Khi JOIN/duyệt các cạnh để tính doanh thu, nếu không khử trùng theo đúng fact và ancestor, một giao dịch có thể bị cộng nhiều lần. Điều này gần với vấn đề **bộ giả hoặc nhân bản do phép nối**, nhưng còn phụ thuộc ngữ nghĩa đồ thị nhiều đường.

### Phân tích: grain trước khi JOIN

Một fact ở mức **OrderLine** có thể tham chiếu Customer, Product và nhiều nhãn sản phẩm. JOIN trực tiếp fact với nhiều nhãn sẽ tạo thêm hàng. Nếu mục tiêu là phân bổ doanh thu theo nhiều nhãn, cần trọng số hoặc quy tắc gán rõ; nếu mục tiêu là doanh thu tổng, phải tránh nhân bản. **SUM(DISTINCT amount)** không giải quyết được lỗi vì nhiều sự kiện khác nhau có thể có cùng số tiền.

## 15. Quy trình thực hành trước khi chấp nhận một phân rã

1. **Xác định R và tập F từ nghiệp vụ.** Kiểm tra phạm vi tenant, thời gian, trạng thái và ngoại lệ; không đoán FD chỉ từ dữ liệu mẫu.
2. **Xác định khóa ứng viên.** Dùng bao đóng X⁺ để tìm siêu khóa và tối thiểu hóa thành khóa ứng viên.
3. **Đề xuất các lược đồ con.** Chỉ rõ tập thuộc tính của từng bảng; kiểm tra hợp của chúng bằng R.
4. **Kiểm tra lossless.** Với hai bảng dùng giao R₁∩R₂ và F⁺; với nhiều bảng dùng chase hoặc chứng minh ghép từng bước.
5. **Kiểm tra preservation.** Xác định FD cục bộ hoặc dùng thuật toán bao đóng theo từng bảng; kiểm tra mọi FD quan trọng.
6. **Kiểm tra 3NF/BCNF của từng bảng.** Đánh giá lợi ích giảm dữ liệu lặp và rủi ro mất phụ thuộc khi ép BCNF.
7. **Thiết kế cơ chế cưỡng chế.** Chuyển khóa và FD thành PK, UNIQUE, FK hoặc cơ chế bổ sung. Không mặc định thiết kế “có bảo toàn FD” đã có constraint vật lý.
8. **Viết truy vấn phản ví dụ.** Tìm dữ liệu có thể sinh bộ giả, bản ghi mồ côi hoặc FD bị vi phạm sau khi cập nhật độc lập.
9. **Thử với dữ liệu và giao dịch đồng thời.** Kiểm tra INSERT, UPDATE, DELETE, chuyển trạng thái và migration; đảm bảo mọi writer tuân thủ cùng bất biến.
10. **Ghi quyết định thiết kế.** Mô tả vì sao chọn 3NF/BCNF, phụ thuộc nào được bảo toàn, quy tắc nào cần JOIN/trigger và mức chấp nhận rủi ro.

### Mẫu ghi nhận kết quả thẩm định

~~~text
Quan hệ gốc: R(A, B, C)
FD nghiệp vụ: { A → B, B → C }
Phân rã dự kiến: { R_AB(A,B), R_BC(B,C) }

Bao phủ thuộc tính: PASS
Khóa ứng viên của R: A
Kiểm tra lossless:
  R_AB ∩ R_BC = {B}
  B+_F = {B,C}
  B+ chứa R_BC → PASS
Kiểm tra dependency preservation:
  A → B được bảo vệ trên R_AB
  B → C được bảo vệ trên R_BC
  → PASS
Khóa/FK dự kiến:
  R_BC: PK(B)
  R_AB: PK(A), FK(B) → R_BC(B)
Quy tắc ngoài phạm vi FD:
  Xác minh NULL, vòng đời, ghi đồng thời và quyền cập nhật.
~~~

Tài liệu như vậy giúp người khác biết điều gì đã được **chứng minh**, điều gì mới được **giả định**, và những điều gì phải được kiểm tra thêm ở cấp vật lý.

## 16. Bài tập tự kiểm tra có hướng dẫn giải

### Bài 1. Phân rã nhị phân có lossless không?

**Đề bài:**

~~~text
R(A,B,C,D)
F = { A → B, B → C }
R₁(A,B), R₂(A,C,D)
~~~

**Hướng dẫn giải:** Giao hai quan hệ là {A}; A⁺_F = {A,B,C}. Tập này chứa R₁={A,B}, nên **phân rã lossless** dù không suy ra D từ A. Chỉ cần giao xác định **một** phía.

### Bài 2. Bảo toàn phụ thuộc?

**Đề bài:** Với cùng R(A,B,C,D), F = {A → B, B → C}, phân rã **AB** và **ACD** có bảo toàn B → C không?

**Hướng dẫn giải:** AB bảo vệ A → B; ACD có A → C. Không có FD cục bộ nào buộc **B → C**. Bao đóng của B theo hợp FD cục bộ chỉ là {B}, nên **không bảo toàn** B → C. Đây là phân rã lossless (bài 1) nhưng không preservation.

### Bài 3. Một bảng chung có đủ?

**Đề bài:** R(Student, Course, Grade), FD (Student, Course) → Grade. Đề xuất tách thành StudentCourse(Student,Course) và StudentGrade(Student,Grade). Có lossless không?

**Hướng dẫn giải:** Giao là {Student}. Từ F chỉ suy ra Grade bằng **cặp (Student,Course)**, không có Student → Course hay Student → Grade. Vì giao không xác định cả hai phía, phân rã **không lossless theo F**. Một sinh viên có hai môn với hai điểm khác nhau sẽ sinh các cặp môn–điểm giả khi nối.

### Bài 4. Chase nhỏ

**Đề bài:** R(A,B,C) → AB và BC; F = {B → C}. Hãy điền tableau và thực hiện chase.

**Hướng dẫn giải:** Hàng AB = (a_A,a_B,b_1C); hàng BC = (b_2A,a_B,a_C). Hai hàng bằng nhau ở B, nên B → C làm b_1C thành a_C. Hàng AB trở thành toàn a ⇒ **lossless**.

### Bài 5. 3NF hay BCNF?

**Đề bài:**

~~~text
R(A,B,C), F = { AB → C, C → B }
~~~

Hãy xác định khóa, kiểm tra BCNF và phân rã theo C → B.

**Hướng dẫn giải:** Hai khóa ứng viên là **AB và AC**. FD C → B vi phạm BCNF vì C không là siêu khóa, nhưng R vẫn đạt 3NF vì B là prime. Phân rã thành **CB và AC** lossless nhờ C → B, song **không bảo toàn AB → C**. Giữ 3NF có thể giúp tránh phải kiểm tra AB → C bằng JOIN xuyên bảng.

### Bài 6. Có thể chứng minh từ dữ liệu thử không?

**Đề bài:** Sau khi phân rã một bảng lớn, JOIN các bảng con trên môi trường thử trả đúng 10.000 hàng, không thừa không thiếu. Có thể kết luận lossless không?

**Hướng dẫn giải:** **Chưa.** Điều đó chỉ cho thấy kết quả đúng trên **dataset thử**. Lossless yêu cầu mọi thể hiện r thỏa F đều khôi phục chính xác; cần chứng minh theo phụ thuộc đã được xác nhận. Dữ liệu mới có thể trùng giá trị tại cột nối và làm lộ phép phân rã sai.

### Bài 7. FD phụ thuộc thời gian

**Đề bài:** Một Course có nhiều giảng viên ở các học kỳ khác nhau. Thiết kế cũ dùng CourseID → InstructorID. Điều gì cần thay đổi trước khi kiểm tra lossless?

**Hướng dẫn giải:** Cần xác nhận FD đúng ở phạm vi nào, chẳng hạn **(CourseID, TermID) → InstructorID** nếu mỗi môn trong một kỳ có đúng một giảng viên, hoặc thêm SectionID nếu có nhiều lớp. Thiết kế khóa và phép phân rã theo FD cũ không còn phản ánh đúng dữ liệu. Mọi phép chứng minh dựa trên FD sai đều không đáng tin.

### Bài 8. Bảo toàn FD nhưng không lossless

**Đề bài:** R(A,B,C), F = {A → B}; phân rã AB và BC. Phụ thuộc có được bảo toàn không? JOIN có lossless không?

**Hướng dẫn giải:** FD A → B nằm trọn trong AB nên **được bảo toàn**. Nhưng giao là B; B⁺={B}, không xác định AB hoặc BC. Phân rã **không lossless**, minh họa tính độc lập của hai tiêu chí.

## 17. Ghi nhớ

- **Lossless join:** chiếu một quan hệ gốc hợp lệ xuống các bảng con rồi nối lại **không sinh thêm bộ giả và không thiếu bộ**.
- **Dependency preservation:** các FD nghiệp vụ ban đầu được suy ra từ hợp các **FD cục bộ** sau phân rã, giúp kiểm tra mà không cần JOIN nhiều bảng.
- Với **phân rã hai bảng dưới các FD**, giao R₁∩R₂ phải xác định **toàn bộ R₁ hoặc toàn bộ R₂**.
- **Lossless và preservation độc lập.** Một thiết kế có thể đạt một tiêu chí nhưng không đạt tiêu chí còn lại.
- **Chase** giúp kiểm tra lossless cho phân rã nhiều bảng; **bao đóng thuộc tính** giúp kiểm tra FD và dependency preservation.
- **3NF synthesis** có thể bảo đảm cả lossless lẫn preservation; **BCNF decomposition** thường lossless nhưng đôi khi làm mất khả năng bảo toàn một số FD.
- Lý thuyết dựa trên **FD đúng theo nghiệp vụ** và ngữ nghĩa quan hệ tập hợp. Trong SQL thực tế còn cần kiểm soát **NULL, bản ghi trùng, PK/FK, giao dịch, cập nhật đồng thời và lịch sử**.

Một phân rã đáng chấp nhận không chỉ giảm số cột lặp. Nó phải giữ được **sự thật nghiệp vụ khi JOIN**, giữ được **quy tắc toàn vẹn có thể cưỡng chế**, đồng thời cân bằng chi phí truy vấn và cập nhật khi hệ thống thay đổi.

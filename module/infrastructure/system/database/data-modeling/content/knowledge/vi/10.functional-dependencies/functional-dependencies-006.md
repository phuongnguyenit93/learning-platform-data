# Phụ thuộc đa trị và những tập giá trị độc lập trong cùng một quan hệ

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, chúng ta chuyển quy tắc nghiệp vụ thành lược đồ dữ liệu có thể kiểm chứng: nhận diện thực thể, quan hệ, khóa, ràng buộc, dạng chuẩn và cách lưu trữ vật lý. **Phụ thuộc đa trị** (*multivalued dependency*, MVD) giúp phát hiện một loại dư thừa mà chỉ phân tích **phụ thuộc hàm** (*functional dependency*, FD) thường chưa tìm ra: hai tập giá trị **độc lập với nhau** lại được lưu chung trong một bảng.

Sau bài học, bạn có thể:

1. Đọc và giải thích ký hiệu \(X\twoheadrightarrow Y\) bằng quy tắc trao đổi giá trị giữa các bộ.
2. Phân biệt **một-nhiều** với **nhiều giá trị độc lập**; xác định khi nào dữ liệu cần đủ các tổ hợp.
3. Nhận diện phụ thuộc đa trị **tầm thường**, **không tầm thường** và liên hệ với phụ thuộc hàm.
4. Dùng phụ thuộc đa trị để kiểm tra **dạng chuẩn 4NF** và thực hiện phân rã **nối không mất mát**.
5. Thiết kế bảng quan hệ và truy vấn SQL đúng mức hạt, tránh giả định sai từ dữ liệu mẫu và tránh tích Descartes ngoài ý muốn.

## 1. Tình huống nghiệp vụ: một người có nhiều kỹ năng và nhiều ngôn ngữ

Giả sử hệ thống quản lý hồ sơ nhân sự lưu:

~~~text
EMPLOYEE_PROFILE(employee_id, skill, language)
~~~

Quy tắc nghiệp vụ được xác nhận:

- Một nhân viên có thể sở hữu **nhiều kỹ năng**.
- Một nhân viên có thể sử dụng **nhiều ngôn ngữ**.
- **Danh sách kỹ năng** và **danh sách ngôn ngữ** được quản lý **độc lập**. Nhân viên biết Java và Python, đồng thời sử dụng tiếng Việt và tiếng Anh; một ngôn ngữ không phải thuộc tính của một kỹ năng cụ thể.

Nếu bảng trên được yêu cầu biểu diễn **đầy đủ các tổ hợp** kỹ năng và ngôn ngữ độc lập, dữ liệu của nhân viên `NV01` sẽ trông như sau:

| employee_id | skill | language |
|---|---|---|
| NV01 | Java | vi |
| NV01 | Java | en |
| NV01 | Python | vi |
| NV01 | Python | en |

Hai danh sách thực tế là:

~~~text
Skills(NV01)    = {Java, Python}
Languages(NV01) = {vi, en}
~~~

Để biểu diễn chúng bằng một quan hệ ba cột, bảng phải lưu:

\[
\{\text{Java},\text{Python}\}\times\{\text{vi},\text{en}\}.
\]

Số bộ là \(2\times2=4\). Nếu nhân viên có 8 kỹ năng và 5 ngôn ngữ, bảng gộp cần \(8\times5=40\) tổ hợp chỉ để diễn đạt 13 giá trị thuộc **hai danh sách**.

Từ đây xuất hiện vấn đề: thêm một ngôn ngữ mới phải thêm nhiều dòng, xóa một kỹ năng phải xóa nhiều dòng, và thiếu một tổ hợp có thể khiến phép đọc nhầm rằng một kỹ năng không đi cùng một ngôn ngữ. **Phụ thuộc đa trị** mô tả chính sự độc lập này.

## 2. Định nghĩa hình thức phụ thuộc đa trị

Xét quan hệ \(R(U)\). Chọn tập thuộc tính \(X,Y\subseteq U\) và đặt:

\[
Z=U-(X\cup Y).
\]

Để diễn giải dễ hơn, ta xem \(X\), \(Y\), \(Z\) thành ba phần rời nhau (nếu \(X\) và \(Y\) chồng nhau, có thể xét \(Y-X\)). Một phụ thuộc đa trị:

\[
X\twoheadrightarrow Y
\]

được hiểu là: **sau khi cố định giá trị \(X\), tập giá trị \(Y\) độc lập với các giá trị của phần thuộc tính còn lại \(Z\)**.

### Điều kiện trao đổi bộ

Cho **bất kỳ hai bộ** \(t_1,t_2\) của một trạng thái quan hệ hợp lệ \(r\), nếu:

\[
t_1[X]=t_2[X],
\]

thì phải tồn tại hai bộ \(t_3,t_4\in r\) sao cho:

| Phần thuộc tính | \(t_3\) lấy từ | \(t_4\) lấy từ |
|---|---|---|
| \(X\) | Cùng giá trị \(X\) của \(t_1,t_2\) | Cùng giá trị \(X\) của \(t_1,t_2\) |
| \(Y\) | \(t_1[Y]\) | \(t_2[Y]\) |
| \(Z\) | \(t_2[Z]\) | \(t_1[Z]\) |

Nói cách khác, khi hai bộ cùng \(X\), ta có thể **hoán đổi phần \(Y\)** trong khi giữ các phần \(Z\), và **cả hai tổ hợp hoán đổi phải tồn tại** trong quan hệ hợp lệ.

Với ví dụ:

~~~text
X = {employee_id}
Y = {skill}
Z = {language}
~~~

Ta có:

\[
\text{employee\_id}\twoheadrightarrow\text{skill}.
\]

Lấy hai bộ:

~~~text
t1 = (NV01, Java,   vi)
t2 = (NV01, Python, en)
~~~

thì các bộ tổ hợp chéo cũng phải có:

~~~text
t3 = (NV01, Java,   en)
t4 = (NV01, Python, vi)
~~~

Khi phần còn lại chỉ là `language`, từ **quy tắc bù** của MVD cũng suy ra:

\[
\text{employee\_id}\twoheadrightarrow\text{language}.
\]

Điều kiện này áp dụng cho **mọi trạng thái dữ liệu hợp lệ theo nghiệp vụ**. Một vài hàng nhìn có vẻ tạo thành tích Descartes chưa đủ chứng minh có phụ thuộc đa trị; tính độc lập phải được người hiểu nghiệp vụ xác nhận.

## 3. “Có nhiều giá trị” không đồng nghĩa với “phụ thuộc đa trị”

Ví dụ, một khóa `order_id` có thể gắn với nhiều `product_id`; đây là quan hệ **một-nhiều**. Điều đó **không tự động** tạo ra một MVD không tầm thường.

Phụ thuộc đa trị trở nên đáng quan tâm khi **cùng một \(X\)** liên quan tới hai nhóm thuộc tính mà lựa chọn ở nhóm này **không ràng buộc** lựa chọn ở nhóm kia. Bảng sau cho thấy ba tình huống khác nhau:

| Tình huống | Quy tắc thực tế | Có nên giả định tích Descartes? |
|---|---|---|
| Nhân viên có các kỹ năng và các ngôn ngữ độc lập | Biết Python không phụ thuộc biết tiếng Anh | **Có**, nếu bảng ba cột buộc biểu diễn hai danh sách trong từng tổ hợp |
| Một lớp học có nhiều sinh viên | `class_id` liên hệ nhiều `student_id` | **Chưa đủ thông tin** để nói có MVD không tầm thường |
| Cửa hàng có phiên bản áo theo **màu–kích thước** chỉ ở một số tổ hợp | Có áo đỏ cỡ M nhưng không có áo đỏ cỡ XL | **Không**: mỗi cặp có thể là một biến thể thực tế riêng |

Ví dụ phản ví dụ: bảng `SKU_VARIANT(product_id, color, size)` có:

| product_id | color | size |
|---|---|---|
| SP01 | đỏ | M |
| SP01 | xanh | XL |

Nếu chỉ có hai phiên bản này thực sự được bán, ta **không được** tự sinh thêm `(SP01, đỏ, XL)` và `(SP01, xanh, M)`. **Màu và kích thước ở đây là cặp kết hợp có ý nghĩa nghiệp vụ**, chứ chưa phải hai danh sách độc lập.

Ngược lại, bảng hồ sơ nhân viên chỉ lưu **danh sách kỹ năng** và **danh sách ngôn ngữ**, nên việc ghép cặp là sản phẩm của cách lưu gộp, không diễn đạt khả năng sử dụng một ngôn ngữ để thực hành một kỹ năng cụ thể.

**Câu hỏi kiểm tra quan trọng:** “Nếu thêm một giá trị \(Y\) cho một \(X\), nghiệp vụ có cho phép và yêu cầu nó đi cùng **mọi** giá trị \(Z\) hiện có của \(X\) hay không?” Nếu câu trả lời là không, phải xem lại giả định MVD.

## 4. Phân biệt FD và MVD

Phụ thuộc hàm:

\[
X\rightarrow Y
\]

nghĩa là **mỗi giá trị \(X\) xác định tối đa một giá trị \(Y\)**.

Phụ thuộc đa trị:

\[
X\twoheadrightarrow Y
\]

cho phép **một \(X\) có cả một tập giá trị \(Y\)**, nhưng tập đó **không phụ thuộc vào các thuộc tính còn lại** của cùng bộ.

| Tiêu chí | FD: \(X\rightarrow Y\) | MVD: \(X\twoheadrightarrow Y\) |
|---|---|---|
| Đối tượng được xác định | Một giá trị \(Y\) cho mỗi \(X\) | Một **tập giá trị** \(Y\) độc lập với \(Z\) cho mỗi \(X\) |
| Cách kiểm tra trên quan hệ | Hai bộ cùng \(X\) phải cùng \(Y\) | Các cặp \(Y,Z\) hoán đổi phải tồn tại |
| Ví dụ | `employee_id → employee_name` trên bảng hiện hành | `employee_id ↠ skill` trên bảng kỹ năng–ngôn ngữ độc lập |
| Dạng chuẩn thường liên quan | 2NF, 3NF, BCNF | **4NF** |

### FD suy ra MVD, nhưng chiều ngược không đúng

Nếu \(X\rightarrow Y\), thì \(X\twoheadrightarrow Y\). Đây là một quy tắc suy diễn cơ bản của MVD.

Lý do: với mỗi \(X\), \(Y\) chỉ có một giá trị, nên mọi phép đổi chỗ \(Y\) giữa các bộ cùng \(X\) đều giữ nguyên giá trị \(Y\) và không gây thiếu tổ hợp.

Tuy nhiên:

~~~text
employee_id ↠ skill
~~~

**không** kéo theo:

~~~text
employee_id → skill
~~~

vì một nhân viên có thể có nhiều kỹ năng.

### MVD độc lập với việc có phụ thuộc hàm không tầm thường

Trong bảng `EMPLOYEE_PROFILE(employee_id, skill, language)`, giả sử mỗi nhân viên có nhiều kỹ năng và nhiều ngôn ngữ, mỗi kỹ năng/ngôn ngữ được nhiều nhân viên chia sẻ. Khi đó không có FD không tầm thường nào từ `employee_id` tới một trong hai cột còn lại.

Nếu các tổ hợp là độc lập, quan hệ có **MVD không tầm thường** nhưng có thể vẫn đạt **BCNF** xét riêng FD. Đây là lý do cần **4NF**.

## 5. MVD tầm thường và không tầm thường

Một MVD \(X\twoheadrightarrow Y\) trên \(R(U)\) là **tầm thường** nếu thỏa **ít nhất một** điều kiện:

\[
Y\subseteq X
\quad\text{hoặc}\quad
X\cup Y=U.
\]

Hai trường hợp này không tạo ra một ràng buộc độc lập mới đối với phần thuộc tính còn lại.

Ví dụ trên `R(employee_id, skill, language)`:

~~~text
{employee_id, skill} ↠ {skill}               # Tầm thường: Y ⊆ X
{employee_id} ↠ {skill, language}             # Tầm thường: X ∪ Y = U
{employee_id} ↠ {skill}                       # Không tầm thường
{employee_id} ↠ {language}                    # Không tầm thường
~~~

Các điều kiện tầm thường/không tầm thường là xét trên **toàn bộ lược đồ của quan hệ**, không chỉ dữ liệu mẫu.

Một quan hệ **chỉ có hai nhóm thuộc tính \(X\) và \(Y\)**, chẳng hạn `EMPLOYEE_SKILLS(employee_id, skill)`, luôn có \(X\cup Y=U\) với MVD `employee_id ↠ skill`; vì thế MVD này **tầm thường trong chính quan hệ hai cột**. Điều đó giải thích tại sao việc tách hai danh sách thành hai bảng có thể loại bỏ vi phạm 4NF ban đầu.

### Quy tắc bù (*complementation*)

Nếu \(X\twoheadrightarrow Y\) trên \(R(U)\) thì:

\[
X\twoheadrightarrow U-(X\cup Y).
\]

Trong bảng ba cột, `employee_id ↠ skill` kéo theo `employee_id ↠ language`. Không cần coi hai phụ thuộc là hai giả định nghiệp vụ độc lập khi phần còn lại chỉ là một tập thuộc tính.

## 6. Từ MVD đến bất thường dữ liệu

Giả sử nhân viên `NV01` biết ba kỹ năng và hai ngôn ngữ:

~~~text
Skills = {Java, Python, SQL}
Languages = {vi, en}
~~~

Bảng gộp cần \(3\times2=6\) dòng. Nếu thêm ngôn ngữ `fr`, phải thêm **ba dòng mới**, một cho mỗi kỹ năng. Nếu quên dòng `(NV01, SQL, fr)`, dữ liệu gộp không còn biểu diễn đúng hai tập độc lập theo quy tắc đã xác nhận.

Các bất thường:

- **Chèn:** muốn thêm ngôn ngữ `ja` phải tạo bản ghi kết hợp với tất cả kỹ năng; nếu nhân viên chưa có kỹ năng được ghi nhận, bảng ba cột không diễn đạt được danh sách ngôn ngữ riêng một cách tự nhiên.
- **Cập nhật:** sửa mã hoặc nhãn kỹ năng đòi sửa mọi dòng ghép với ngôn ngữ; nếu sửa thiếu, hồ sơ có giá trị không nhất quán.
- **Xóa:** xóa một dòng ghép `Java–en` riêng lẻ có thể làm mất một tổ hợp bắt buộc mà không có ý nghĩa “nhân viên mất kỹ năng Java” hay “không còn dùng tiếng Anh”.
- **Dung lượng và truy vấn:** số dòng cho một nhân viên tăng theo **tích** của hai số lượng thay vì theo **tổng**, gây tốn lưu trữ và dễ đếm trùng.

Với \(m\) kỹ năng và \(n\) ngôn ngữ, mô hình tích tổ hợp cần \(mn\) dòng; sau phân rã thành hai quan hệ độc lập, cần \(m+n\) dòng liên kết. Với \(m=n=20\), đó là **400 so với 40** dòng liên kết cho một nhân viên (chưa tính bảng thực thể nhân viên).

Đây là bài toán dư thừa do MVD; nó vẫn có thể xuất hiện khi phân tích FD không tìm được phụ thuộc vi phạm BCNF.

## 7. Dạng chuẩn 4NF và điều kiện vi phạm

Một quan hệ \(R\) ở **dạng chuẩn bốn (Fourth Normal Form, 4NF)** đối với các phụ thuộc đã xác nhận nếu, với **mọi phụ thuộc đa trị không tầm thường** \(X\twoheadrightarrow Y\) đúng trên \(R\), **\(X\) phải là siêu khóa** của \(R\).

\[
R\text{ đạt 4NF}
\iff
\forall (X\twoheadrightarrow Y)\text{ không tầm thường}:
\ X\text{ là siêu khóa}.
\]

Trong `EMPLOYEE_PROFILE(employee_id, skill, language)`:

- `employee_id ↠ skill` không tầm thường vì `skill` không thuộc `employee_id` và vẫn còn cột `language`.
- `employee_id` **không phải siêu khóa**, vì một nhân viên có nhiều dòng với các kỹ năng và ngôn ngữ khác nhau.
- Do đó bảng gộp **vi phạm 4NF**, dưới các quy tắc độc lập đã xác nhận.

### BCNF chưa chắc đủ

BCNF chỉ kiểm soát mọi **FD không tầm thường** phải có vế trái là siêu khóa. Mọi FD đều kéo theo MVD, nhưng không phải MVD nào cũng suy ra FD. Vì vậy một bảng có thể **đạt BCNF** nhưng **không đạt 4NF**.

Không nên cố tạo một FD giả như `employee_id → skill` để giải thích vấn đề; phụ thuộc này **sai** nếu mỗi nhân viên có nhiều kỹ năng.

### Điều kiện “siêu khóa” được xác định thế nào?

Một tập \(X\) là siêu khóa nếu \(X^+=U\) theo **các phụ thuộc hàm hợp lệ** của quan hệ (nói cách khác, \(X\rightarrow U\)). MVD đơn thuần **không** làm \(X\) trở thành siêu khóa. Trong ví dụ, việc `employee_id ↠ skill` và `employee_id ↠ language` cùng đúng vẫn không cho `employee_id → skill` hoặc `employee_id → language`.

## 8. Phân rã lược đồ theo MVD: nối không mất mát

Với \(R(X,Y,Z)\), nếu phụ thuộc đa trị \(X\twoheadrightarrow Y\) được xác nhận, ta có thể phân rã:

\[
R(X,Y,Z)\ \longrightarrow\ R_1(X,Y),\ R_2(X,Z).
\]

Trong mô hình quan hệ theo **ngữ nghĩa tập hợp**, phụ thuộc đa trị này tương đương với đẳng thức:

\[
r=\pi_{XY}(r)\bowtie\pi_{XZ}(r).
\]

Đây là **phân rã nối không mất mát** (*lossless-join decomposition*): khi chiếu ra hai quan hệ rồi nối tự nhiên trên \(X\), dữ liệu hợp lệ ban đầu được khôi phục chính xác, không tạo những bộ sai.

### Thực hiện trên dữ liệu nhân viên

Thay:

~~~text
EMPLOYEE_PROFILE(employee_id, skill, language)
~~~

bằng:

~~~text
EMPLOYEE_SKILLS(employee_id, skill)
EMPLOYEE_LANGUAGES(employee_id, language)
~~~

Dữ liệu lúc này là:

**EMPLOYEE_SKILLS**

| employee_id | skill |
|---|---|
| NV01 | Java |
| NV01 | Python |

**EMPLOYEE_LANGUAGES**

| employee_id | language |
|---|---|
| NV01 | vi |
| NV01 | en |

Nếu cần tạo lại **bảng tổ hợp độc lập**, có thể nối hai bảng trên `employee_id` và thu được đúng bốn dòng ở phần mở đầu. Tuy nhiên, trong nghiệp vụ bình thường, muốn lấy kỹ năng hoặc ngôn ngữ của nhân viên thì nên **truy vấn đúng bảng liên kết**, không cần tạo ra các cặp tổ hợp.

### Lưu ý: phân rã chỉ lossless khi MVD thực sự đúng

Với bảng `SKU_VARIANT(product_id,color,size)` có hai bộ `(SP01,đỏ,M)` và `(SP01,xanh,XL)`, phép tách thành danh sách màu và danh sách kích thước rồi nối lại sẽ tạo thêm hai biến thể **không có thật**. Vì không có MVD độc lập, đây là **phân rã mất mát thông tin** (*lossy*): sau phép nối xuất hiện bộ giả.

Đừng phân rã chỉ vì thấy một thực thể có hai thuộc tính nhận nhiều giá trị; phải xác nhận các **tổ hợp có bắt buộc tồn tại và được phép tồn tại hay không**.

## 9. Thiết kế lược đồ vật lý và ràng buộc

Ví dụ SQL với khóa chính, khóa ngoại và hai bảng liên kết độc lập:

~~~sql
CREATE TABLE employees (
    employee_id VARCHAR(30) PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE skills (
    skill_code VARCHAR(50) PRIMARY KEY,
    skill_name VARCHAR(200) NOT NULL
);

CREATE TABLE languages (
    language_code VARCHAR(10) PRIMARY KEY,
    language_name VARCHAR(100) NOT NULL
);

CREATE TABLE employee_skills (
    employee_id VARCHAR(30) NOT NULL REFERENCES employees(employee_id),
    skill_code VARCHAR(50) NOT NULL REFERENCES skills(skill_code),
    PRIMARY KEY (employee_id, skill_code)
);

CREATE TABLE employee_languages (
    employee_id VARCHAR(30) NOT NULL REFERENCES employees(employee_id),
    language_code VARCHAR(10) NOT NULL REFERENCES languages(language_code),
    PRIMARY KEY (employee_id, language_code)
);
~~~

Mỗi bảng liên kết có mức hạt và khóa riêng:

| Bảng | Một dòng biểu diễn | Khóa ứng viên minh họa |
|---|---|---|
| `employees` | Một nhân viên | `employee_id` |
| `employee_skills` | Một kỹ năng của một nhân viên | `(employee_id, skill_code)` |
| `employee_languages` | Một ngôn ngữ của một nhân viên | `(employee_id, language_code)` |

Những khóa chính này ngăn trùng dòng liên kết. Khóa ngoại bảo đảm nhân viên, kỹ năng, ngôn ngữ được tham chiếu có tồn tại. Chúng không tự suy ra quy tắc khác như **mức độ thành thạo**, **thời gian hiệu lực** hoặc **kiểm tra chứng chỉ**; các quy tắc đó cần mô hình thêm khi nghiệp vụ yêu cầu.

### Truy vấn các danh sách độc lập

~~~sql
-- Lấy danh sách kỹ năng, không nhân bản theo số ngôn ngữ.
SELECT es.skill_code
FROM employee_skills AS es
WHERE es.employee_id = 'NV01'
ORDER BY es.skill_code;

-- Lấy danh sách ngôn ngữ, không nhân bản theo số kỹ năng.
SELECT el.language_code
FROM employee_languages AS el
WHERE el.employee_id = 'NV01'
ORDER BY el.language_code;
~~~

Khi cố ý tạo tất cả tổ hợp cho việc minh họa:

~~~sql
SELECT
    es.employee_id,
    es.skill_code,
    el.language_code
FROM employee_skills AS es
JOIN employee_languages AS el
    ON es.employee_id = el.employee_id
WHERE es.employee_id = 'NV01';
~~~

Truy vấn `JOIN` này là **tích tổ hợp có chủ đích**, không phải bằng chứng rằng nhân viên thực hiện từng kỹ năng bằng từng ngôn ngữ. Dùng kết quả để tính số kỹ năng hoặc số ngôn ngữ bằng `COUNT(*)` sẽ đếm trùng; cần đếm ở từng bảng gốc hoặc dùng `COUNT(DISTINCT ...)` theo mục đích.

Về hiệu năng, khóa chính ghép thường cung cấp một đường truy cập thuận lợi theo `employee_id`, nhưng tùy hệ quản trị và mẫu truy vấn, có thể cần thêm chỉ mục trên `skill_code` hoặc `language_code` để tra ngược. **MVD quyết định cấu trúc logic; chỉ mục quyết định chiến lược truy cập vật lý.**

## 10. SQL kiểm tra phản ví dụ MVD trong dữ liệu hiện có

Một MVD không phải lúc nào cũng có thể suy ra bằng nhìn vài bộ. Tuy nhiên, nếu đã có giả định độc lập, ta có thể dùng dữ liệu để phát hiện **tổ hợp bị thiếu**.

Giả sử `staging_employee_profile(employee_id, skill_code, language_code)` dự kiến lưu **đầy đủ mọi tổ hợp**. Truy vấn dưới đây tạo mọi cặp kỹ năng–ngôn ngữ xuất hiện cho cùng nhân viên, rồi tìm cặp không có trong bảng:

~~~sql
WITH observed AS (
    SELECT DISTINCT employee_id, skill_code, language_code
    FROM staging_employee_profile
    WHERE employee_id IS NOT NULL
      AND skill_code IS NOT NULL
      AND language_code IS NOT NULL
),
missing_combinations AS (
    SELECT DISTINCT
        s.employee_id,
        s.skill_code,
        l.language_code
    FROM observed AS s
    JOIN observed AS l
      ON l.employee_id = s.employee_id
    WHERE NOT EXISTS (
        SELECT 1
        FROM observed AS o
        WHERE o.employee_id = s.employee_id
          AND o.skill_code = s.skill_code
          AND o.language_code = l.language_code
    )
)
SELECT employee_id, skill_code, language_code
FROM missing_combinations
ORDER BY employee_id, skill_code, language_code;
~~~

Ví dụ, nếu staging có `(NV01,Java,vi)` và `(NV01,Python,en)` nhưng thiếu hai cặp chéo, truy vấn trả về `(NV01,Java,en)` và `(NV01,Python,vi)`. Đây là **phản ví dụ với yêu cầu đóng dưới phép kết hợp** trên tập dữ liệu staging đã xét.

**Giới hạn quan trọng:**

- Truy vấn bỏ qua hàng có `NULL`; phải xử lý ý nghĩa dữ liệu thiếu riêng.
- Không có dòng nào trả về chỉ nói rằng **mẫu hiện tại** không có tổ hợp thiếu, chứ không chứng minh MVD là quy tắc nghiệp vụ.
- Nếu những cặp bị thiếu **thực sự không được phép** (chẳng hạn màu–kích thước của SKU), lỗi nằm ở **giả định độc lập**, không phải ở dữ liệu.
- Nếu hai danh sách không nhất thiết phải cùng có phần tử, quan hệ ba cột và phép nối của nó không biểu diễn được chính xác trạng thái “có kỹ năng nhưng chưa có ngôn ngữ”; hai bảng độc lập cùng bảng cha biểu diễn tốt hơn.
- Với SQL, cách xử lý trùng bộ và `NULL` không hoàn toàn giống quan hệ lý thuyết theo ngữ nghĩa tập hợp. CTE dùng `DISTINCT` để kiểm tra tổ hợp giá trị trên các dòng không NULL.

Đây là **kiểm tra hỗ trợ** sau khi đã xác nhận nghiệp vụ; nó không thay thế việc hỏi người sở hữu quy tắc.

## 11. Quy trình nhận diện MVD trong yêu cầu thực tế

### Bước 1 — Xác định thực thể và mức hạt

“Mỗi dòng đang biểu diễn một bản ghi độc lập hay một phép ghép của hai danh sách?” Với `EMPLOYEE_PROFILE`, một dòng `(nhân viên,kỹ năng,ngôn ngữ)` không phải sự kiện nghiệp vụ riêng nếu kỹ năng và ngôn ngữ không có liên hệ từng cặp.

### Bước 2 — Liệt kê các tập giá trị của cùng một thực thể

Ví dụ:

~~~text
employee_id ↦ tập kỹ năng
employee_id ↦ tập ngôn ngữ
~~~

Việc liệt kê này **chưa đủ** để khẳng định MVD; phải kiểm tra sự độc lập.

### Bước 3 — Hỏi rõ việc thêm/xóa giá trị có ảnh hưởng tập kia không

Một số câu hỏi hữu ích:

- Khi thêm ngôn ngữ cho nhân viên, có bắt buộc tạo một tổ hợp với **mọi kỹ năng hiện có** không?
- Có tồn tại khái niệm “**sử dụng kỹ năng này bằng ngôn ngữ kia**” cần lưu theo cặp không?
- Có tổ hợp nào **bị cấm** hoặc **không có thật** dù từng giá trị xuất hiện riêng lẻ không?
- Một danh sách có thể rỗng trong khi danh sách còn lại có phần tử không?
- Phạm vi thời gian, chi nhánh hoặc phiên bản có làm thay đổi tính độc lập không?

Nếu có một quan hệ thực sự giữa \(Y\) và \(Z\) theo từng cặp, phải mô hình hóa quan hệ đó; không tách chỉ vì các cột đều đa trị.

### Bước 4 — Chốt MVD, kiểm tra 4NF và tách lược đồ

Khi \(X\twoheadrightarrow Y\) là MVD **không tầm thường** và \(X\) không phải siêu khóa, quan hệ vi phạm 4NF. Tách `R(X,Y,Z)` thành `R1(X,Y)`, `R2(X,Z)` khi đúng MVD; đối chiếu **lossless** và những ràng buộc cần thực thi.

### Bước 5 — Kiểm chứng bằng nghiệp vụ và dữ liệu

Sau phân rã, thử các thao tác: thêm ngôn ngữ, xóa kỹ năng, nhân viên chưa có kỹ năng, và các trường hợp lịch sử. Kiểm tra truy vấn không tạo bản ghi sai hoặc đếm trùng. Xem xét khóa, khóa ngoại, chính sách `NULL`, chỉ mục, migration và tính toàn vẹn giữa các bảng.

## 12. MVD, dạng chuẩn 5NF và các mô hình dữ liệu khác

**4NF** giải quyết dư thừa do **MVD không tầm thường** có vế trái không là siêu khóa. Ở mức tổng quát hơn, **phụ thuộc nối** (*join dependency*, JD) mô tả trường hợp một quan hệ có thể được tái tạo bằng phép nối **nhiều hơn hai phép chiếu**. **5NF** (project-join normal form) liên quan tới những JD không tầm thường chưa được xử lý ở các dạng chuẩn trước đó; không nên mặc định mọi vấn đề có ba cột đều là MVD hoặc 4NF.

Trong những hệ lưu trữ khác:

| Mô hình | Cách diễn đạt hai danh sách độc lập | Cần chú ý |
|---|---|---|
| **Quan hệ** | Hai bảng liên kết `employee_skills`, `employee_languages` | Khóa ghép, khóa ngoại, 4NF, truy vấn join |
| **Document** | Hai mảng `skills[]`, `languages[]` trong cùng document nhân viên | Xác nhận độc lập, kích thước document, cập nhật mảng và truy vấn |
| **Đồ thị** | Các cạnh `HAS_SKILL` và `USES_LANGUAGE` từ nút nhân viên | Không tự tạo cạnh liên hệ từng kỹ năng với từng ngôn ngữ |
| **Phân tích** | Hai bridge table/factless fact tương ứng hoặc hai mối liên kết dimension | Tránh join hai chiều nhiều-nhiều gây nhân số liệu, xác định mức hạt |

Trong mô hình document, nhiều tập giá trị **có thể nằm trong một document** nếu phù hợp workload; không nhất thiết phải tách vật lý như quan hệ. Quy tắc **độc lập về ngữ nghĩa** vẫn cần được nêu rõ để tránh xây dựng các tổ hợp không có ý nghĩa.

## 13. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: “Có một-nhiều thì chắc chắn có MVD cần tách”.** Chưa đủ. MVD không tầm thường xuất hiện khi có nhóm \(Y\) độc lập với **phần còn lại \(Z\)** trong cùng quan hệ.

**Nhầm lẫn 2: “MVD là FD với vế phải nhiều cột”.** Sai. `X → YZ` vẫn nói về **một giá trị xác định** cho mỗi cột ở vế phải theo \(X\). `X ↠ Y` nói về **tập giá trị \(Y\)** độc lập với \(Z\).

**Nhầm lẫn 3: “Bảng đạt BCNF thì không còn dư thừa”.** Sai. Phụ thuộc đa trị không tầm thường có thể tồn tại mà không có FD không tầm thường vi phạm BCNF; 4NF xử lý trường hợp này.

**Nhầm lẫn 4: “Thiếu tổ hợp là lỗi dữ liệu bất kể nghiệp vụ”.** Sai. Nếu một cặp màu–kích thước thực sự không tồn tại, không được tự thêm cặp để thỏa một MVD giả.

**Nhầm lẫn 5: “Sau khi tách, cứ join hai danh sách là dữ liệu chi tiết có nghĩa”.** Sai. Join tạo **tổ hợp tất cả cặp**; đối với các danh sách độc lập, những cặp đó không phải sự kiện thực tế. Hãy đọc từng bảng theo câu hỏi cần trả lời.

**Nhầm lẫn 6: “MVD luôn cần diễn đạt cả hai chiều bằng hai ràng buộc riêng”.** Với phần thuộc tính còn lại \(Z=U-(X\cup Y)\), quy tắc bù cho thấy \(X\twoheadrightarrow Y\) kéo theo \(X\twoheadrightarrow Z\).

## 14. Bài luyện tập có lời giải

### Bài 1 — Hai tập độc lập

Một tác giả có các **thể loại viết** `{trinh thám, khoa học}` và các **kênh liên lạc** `{email, điện thoại, mạng xã hội}`. Hai danh sách độc lập. Nếu lưu trong `AUTHOR_PROFILE(author_id, genre, contact_channel)`, mỗi tác giả cần bao nhiêu dòng khi cả hai danh sách đều có đầy đủ phần tử?

**Lời giải:** \(2\times3=6\) dòng tổ hợp. Nếu `author_id ↠ genre` là MVD không tầm thường và `author_id` không là siêu khóa, bảng vi phạm 4NF. Có thể tách `AUTHOR_GENRES(author_id,genre)` và `AUTHOR_CONTACT_CHANNELS(author_id,contact_channel)` để lưu \(2+3=5\) dòng liên kết.

### Bài 2 — Phụ thuộc đa trị có thật không?

Bảng `CAR_VARIANT(model_id,color,engine)` chứa `(M1,đỏ,xăng)` và `(M1,xanh,điện)`. Nhà sản xuất **không có** biến thể `đỏ,điện`. Có thể kết luận `model_id ↠ color` không?

**Lời giải:** Không. Nếu MVD đúng, từ hai bộ cùng `model_id` phải tồn tại các bộ hoán đổi `(M1,đỏ,điện)` và `(M1,xanh,xăng)`. Khi một trong những tổ hợp ấy không được phép, MVD **sai với nghiệp vụ đã cho**. Cần giữ quan hệ biến thể theo cặp màu–động cơ có thật.

### Bài 3 — MVD tầm thường

Trên `R(employee_id,skill,language)`, phân loại:

1. `(employee_id,skill) ↠ skill`.
2. `employee_id ↠ (skill,language)`.
3. `employee_id ↠ skill`.

**Lời giải:** (1) **Tầm thường** vì vế phải nằm trong vế trái. (2) **Tầm thường** vì hợp vế trái–phải phủ toàn bộ lược đồ. (3) **Không tầm thường**; chỉ đúng khi các tập kỹ năng và ngôn ngữ độc lập theo quy tắc nghiệp vụ.

### Bài 4 — FD và MVD

Trong bảng nhân viên hiện hành, `employee_id → display_name`. Có thể suy ra `employee_id ↠ display_name` không? Ngược lại, từ `employee_id ↠ skill` có thể suy ra `employee_id → skill` không?

**Lời giải:** **Có** cho câu thứ nhất, vì FD suy ra MVD. **Không** cho câu thứ hai, vì một nhân viên có thể có nhiều kỹ năng mà danh sách ấy vẫn độc lập với các thuộc tính còn lại.

### Bài 5 — Kiểm tra 4NF

Cho `R(student_id,club_id,hobby_id)`. Mỗi sinh viên tham gia nhiều câu lạc bộ và có nhiều sở thích **độc lập**, không có FD không tầm thường nào khác. `student_id` có phải siêu khóa không? Quan hệ có đạt 4NF không?

**Lời giải:** `student_id` không phải siêu khóa vì một sinh viên có nhiều giá trị của hai cột còn lại. Theo nghiệp vụ, `student_id ↠ club_id` là MVD không tầm thường; do đó quan hệ **không đạt 4NF** dù có thể đạt BCNF. Tách `STUDENT_CLUBS(student_id,club_id)` và `STUDENT_HOBBIES(student_id,hobby_id)`.

### Bài 6 — Dữ liệu bị thiếu hay quy tắc bị sai?

Staging lưu:

~~~text
(NV02, SQL, vi)
(NV02, Java, en)
~~~

Người phụ trách xác nhận kỹ năng và ngôn ngữ là **hai danh sách độc lập** của nhân viên. Hãy nêu kết quả kiểm tra MVD.

**Lời giải:** Dữ liệu staging **thiếu** `(NV02,SQL,en)` và `(NV02,Java,vi)` nếu bảng gộp yêu cầu tất cả tổ hợp. Cần đối chiếu dữ liệu nguồn hoặc chuyển sang hai bảng độc lập. Nếu thực tế hai cột biểu diễn **kỹ năng được thực hành bằng ngôn ngữ cụ thể**, việc thiếu cặp chéo có thể hợp lệ và khi đó không có MVD như giả định. Chỉ được sửa sau khi xác nhận ý nghĩa bảng.

## 15. Checklist trước khi chốt mô hình

- [ ] Đã xác định **mức hạt** mỗi dòng và ý nghĩa của từng nhóm thuộc tính.
- [ ] Đã xác nhận hai tập giá trị thực sự **độc lập theo nghiệp vụ**; việc thêm một giá trị ở tập này không ràng buộc tập kia.
- [ ] Đã kiểm tra điều kiện trao đổi bộ và có hay không các tổ hợp bị cấm.
- [ ] Đã phân biệt FD \(X\rightarrow Y\) và MVD \(X\twoheadrightarrow Y\).
- [ ] Đã phân biệt MVD tầm thường và không tầm thường trên **toàn lược đồ**.
- [ ] Đã kiểm tra vế trái MVD không tầm thường có là siêu khóa để đánh giá 4NF.
- [ ] Chỉ phân rã thành \(R(X,Y)\) và \(R(X,Z)\) khi có căn cứ để **nối không mất mát**.
- [ ] Đã thiết kế khóa ghép, khóa ngoại, cách truy vấn và chỉ mục cho từng bảng liên kết.
- [ ] Đã kiểm tra tình huống một danh sách rỗng, dữ liệu lịch sử, `NULL` và các trường hợp ngoại lệ.
- [ ] Đã tránh dùng phép join các danh sách độc lập như thể đó là những sự kiện ghép cặp thực tế.

**Ghi nhớ:** **Phụ thuộc đa trị** \(X\twoheadrightarrow Y\) mô tả một **tập giá trị \(Y\)** độc lập với các thuộc tính còn lại khi cố định \(X\). Chính tính độc lập, chứ không phải việc một cột có nhiều giá trị, tạo ra nhu cầu phân rã để đạt **4NF**. Khi mô hình hóa, hãy xác nhận điều kiện trao đổi bộ từ nghiệp vụ trước, rồi mới dùng phép tách và SQL để kiểm chứng.

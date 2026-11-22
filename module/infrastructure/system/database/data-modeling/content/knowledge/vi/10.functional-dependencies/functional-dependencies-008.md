# Phân rã nối không mất mát và tiêu chí khôi phục đúng dữ liệu

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, việc tách một quan hệ lớn thành các bảng có mức hạt rõ ràng giúp giảm dư thừa, thiết kế khóa và ràng buộc tốt hơn. Tuy nhiên, phân rã chỉ an toàn khi **các quan hệ con giữ đủ thông tin để khôi phục chính xác quan hệ ban đầu**. Đây là yêu cầu **nối không mất mát** (*lossless-join decomposition*).

Sau bài học thuộc chương **Phụ thuộc dữ liệu**, bạn có thể:

1. Phát biểu định nghĩa hình thức của phân rã nối không mất mát và giải thích thế nào là **bộ giả** (*spurious tuple*).
2. Áp dụng tiêu chí **giao thuộc tính xác định một trong hai quan hệ con** cho phép phân rã hai bảng dựa trên phụ thuộc hàm (FD).
3. Phân biệt một phân rã **nối không mất mát** với phân rã **bảo toàn phụ thuộc** (*dependency preserving*).
4. Kiểm tra phân rã thành ba bảng trở lên bằng lập luận từng bước hoặc bằng phương pháp **tableau/chase**.
5. Dùng SQL để tìm phản ví dụ trên dữ liệu hiện có, đồng thời hiểu giới hạn của phép kiểm tra bằng dữ liệu mẫu.
6. Liên hệ kết quả với chuẩn hóa 3NF/BCNF/4NF, lược đồ vật lý và việc lựa chọn mô hình quan hệ, document, đồ thị, phân tích.

## 1. Tại sao tách bảng có thể làm sai dữ liệu?

Giả sử hệ thống quản lý đào tạo có quan hệ:

~~~text
STUDENT_TUTOR(student_id, course_id, tutor_id)
~~~

Mỗi dòng ghi nhận **một sinh viên học một môn với một gia sư cụ thể**. Dữ liệu:

| student_id | course_id | tutor_id |
|---|---|---|
| SV01 | C01 | GV01 |
| SV02 | C01 | GV02 |

Một nhà thiết kế tách quan hệ thành:

~~~text
STUDENT_COURSE(student_id, course_id)
COURSE_TUTOR(course_id, tutor_id)
~~~

Khi nối trên `course_id`, ta thu được:

| student_id | course_id | tutor_id | Nguồn gốc |
|---|---|---|---|
| SV01 | C01 | GV01 | Dòng gốc |
| SV01 | C01 | GV02 | **Bộ giả** |
| SV02 | C01 | GV01 | **Bộ giả** |
| SV02 | C01 | GV02 | Dòng gốc |

Hai bảng riêng lẻ cho biết **sinh viên nào học môn nào** và **gia sư nào dạy môn nào**, nhưng đã đánh mất thông tin **gia sư nào kèm sinh viên nào**. Phép nối tạo thêm hai cặp chưa từng được phân công.

Đó là một phân rã **nối mất mát** (*lossy decomposition*). Từ “mất mát” không nhất thiết có nghĩa mất giá trị `SV01` hay `GV01`; điều bị mất là **thông tin về sự kết hợp đúng giữa các thuộc tính**.

Nếu nghiệp vụ quy định **mỗi môn chỉ có đúng một gia sư**, thì `course_id → tutor_id` có thể đúng và tình huống trên không còn hợp lệ. Khi ấy phép phân rã hai bảng có thể nối không mất mát. Kết luận phụ thuộc vào **quy tắc nghiệp vụ**, không phụ thuộc vào trực giác rằng các bảng có chung cột.

## 2. Định nghĩa hình thức: chiếu rồi nối phải bằng đúng quan hệ gốc

Cho lược đồ quan hệ \(R(U)\), trong đó \(U\) là tập thuộc tính. Giả sử phân rã thành \(R_1(U_1),R_2(U_2),\ldots,R_n(U_n)\), với:

\[
U_1\cup U_2\cup\cdots\cup U_n=U.
\]

Ký hiệu \(\pi_{U_i}(r)\) là **phép chiếu** một trạng thái dữ liệu \(r\) của \(R\) lên các thuộc tính \(U_i\). Ký hiệu \(\bowtie\) là **nối tự nhiên**, nối các bộ có giá trị bằng nhau ở thuộc tính chung.

Phân rã được gọi là **nối không mất mát theo tập ràng buộc \(\Sigma\)** khi:

\[
\boxed{
\forall r\models\Sigma,\quad
r=\pi_{U_1}(r)\bowtie\pi_{U_2}(r)
\bowtie\cdots\bowtie\pi_{U_n}(r)
}
\]

Trong đó \(r\models\Sigma\) nghĩa là trạng thái \(r\) tuân thủ **mọi ràng buộc nghiệp vụ đã xác nhận** thuộc tập \(\Sigma\). Tập \(\Sigma\) có thể chứa FD, MVD, JD hoặc những ràng buộc khác tùy bài toán.

Định nghĩa có hai yêu cầu đồng thời:

- **Không thiếu bộ gốc:** mọi bộ trong \(r\) phải được tái tạo sau khi nối.
- **Không có bộ giả:** kết quả nối không được tạo thêm bộ không thuộc \(r\).

Với các phép chiếu của **cùng một quan hệ gốc** theo ngữ nghĩa **tập hợp** của mô hình quan hệ và các tập thuộc tính bao phủ \(U\), mọi bộ gốc luôn xuất hiện trong phép nối:

\[
r\subseteq \bowtie_i\pi_{U_i}(r).
\]

Vì vậy trong bối cảnh này, để chứng minh lossless, vấn đề cốt lõi là chứng minh **không sinh thêm bộ giả**. Nếu các bảng con được tạo độc lập thay vì là phép chiếu từ một quan hệ, còn phải kiểm tra cả tính đầy đủ dữ liệu và tính nhất quán của dữ liệu đầu vào.

### Hai thuật ngữ cần phân biệt

| Thuật ngữ | Nghĩa chính xác | Ví dụ |
|---|---|---|
| **Nối không mất mát** (*lossless join*) | Chiếu ra các bảng con rồi nối trả về **đúng tập bộ gốc** với mọi trạng thái hợp lệ | Tách đơn hàng và dòng hàng khi mã đơn xác định thông tin đơn |
| **Nối mất mát** (*lossy join*) | Có trạng thái hợp lệ mà nối sinh **bộ giả** | Tách phân công sinh viên–môn–gia sư khi không có quy tắc một gia sư cho mỗi môn |

“Lossless” là **tính chất của phép phân rã dưới các ràng buộc**. Một truy vấn `JOIN` tình cờ trả đúng kết quả trên vài dòng mẫu chưa chứng minh toàn bộ thiết kế lossless.

## 3. Điều kiện cần và đủ cho phân rã hai quan hệ theo phụ thuộc hàm

Xét phân rã:

\[
R(U)\longrightarrow R_1(U_1), R_2(U_2),
\qquad U_1\cup U_2=U.
\]

Đặt \(I=U_1\cap U_2\) là tập thuộc tính **giao**. Khi tập ràng buộc đang xét **chỉ gồm các phụ thuộc hàm \(F\)**, phân rã hai quan hệ là **nối không mất mát theo \(F\)** khi và chỉ khi:

\[
\boxed{
F\models I\rightarrow U_1
\quad\text{hoặc}\quad
F\models I\rightarrow U_2
}
\]

Nói dễ hiểu: **các cột chung phải xác định được tất cả cột của ít nhất một bảng con**.

Nếu \(I\) chính là một khóa của \(R_1\) hoặc \(R_2\) theo các phụ thuộc suy ra từ \(F\), điều kiện trên thỏa mãn. Điều kiện không yêu cầu \(I\) là khóa của **cả hai** bảng.

### Vì sao tiêu chí này hoạt động?

Giả sử \(I\rightarrow U_1\). Khi hai bộ ở \(R_1\) và \(R_2\) trùng giá trị trên \(I\), phần còn lại ở \(R_1\) đã bị \(I\) xác định duy nhất. Bởi vậy việc nối không thể tùy tiện ghép hai biến thể khác nhau của phần \(U_1-I\) với một giá trị \(I\). Khi các bảng là phép chiếu của cùng một quan hệ hợp lệ, mỗi bộ nối được phải tương ứng với một bộ gốc.

### Kiểm tra bằng bao đóng

Không cần liệt kê mọi phụ thuộc suy ra trong \(F^+\). Chỉ cần tính:

\[
I_F^+.
\]

Sau đó kiểm tra:

~~~text
Nếu U1 ⊆ I+ hoặc U2 ⊆ I+:
    phân rã hai bảng lossless theo F
Ngược lại:
    phân rã không được bảo đảm lossless chỉ bởi các FD trong F
~~~

Với điều kiện đã giới hạn **chỉ theo FD**, trường hợp không thỏa cả hai tiêu chí đồng nghĩa phép phân rã không lossless **cho mọi quan hệ thỏa F**: tồn tại trạng thái hợp lệ tạo bộ giả. Nếu có thêm **MVD/JD** làm ràng buộc, một phân rã vẫn có thể lossless dù không thỏa tiêu chí FD này.

## 4. Ví dụ đúng: tách đơn hàng và dòng hàng

Giả sử bảng gộp:

~~~text
ORDER_LINE_FLAT(
    order_id, customer_id,
    line_no, product_id, quantity
)
~~~

Mức hạt của một dòng là **một dòng hàng trong một đơn**. Nghiệp vụ xác nhận:

~~~text
F = {
    order_id            → customer_id,
    (order_id, line_no) → product_id, quantity
}
~~~

Đề xuất phân rã:

~~~text
ORDERS(order_id, customer_id)
ORDER_ITEMS(order_id, line_no, product_id, quantity)
~~~

Kiểm tra:

1. \(U_1=\{\text{order_id},\text{customer_id}\}\).
2. \(U_2=\{\text{order_id},\text{line_no},\text{product_id},\text{quantity}\}\).
3. Giao \(I=U_1\cap U_2=\{\text{order_id}\}\).
4. Từ \(F\): \(\text{order_id}\rightarrow\text{customer_id}\).
5. Theo phản xạ và hợp phụ thuộc, \(\text{order_id}\rightarrow\{\text{order_id},\text{customer_id}\}=U_1\).

Vậy phân rã **nối không mất mát** theo \(F\).

### Thấy rõ bằng dữ liệu

**ORDER_LINE_FLAT**

| order_id | customer_id | line_no | product_id | quantity |
|---|---|---:|---|---:|
| DH01 | KH01 | 1 | SP01 | 2 |
| DH01 | KH01 | 2 | SP02 | 1 |
| DH02 | KH02 | 1 | SP01 | 3 |

Chiếu thành:

~~~text
ORDERS:
    (DH01, KH01)
    (DH02, KH02)

ORDER_ITEMS:
    (DH01, 1, SP01, 2)
    (DH01, 2, SP02, 1)
    (DH02, 1, SP01, 3)
~~~

Nối trên `order_id` khôi phục **chính xác ba dòng gốc**. Điều này minh họa kết luận đã chứng minh từ FD; bản thân ví dụ ba dòng **không phải bằng chứng tổng quát**.

### Khi thiếu điều kiện nghiệp vụ

Nếu một `order_id` có thể bị tái sử dụng **giữa hai cửa hàng**, quy tắc `order_id → customer_id` có thể sai trên tập dữ liệu toàn hệ thống. Khi đó cần làm rõ mã toàn cục hoặc dùng cặp `(store_id, order_id)` trong cả hai bảng con và trong phép nối.

Nối trên khóa thiếu **phạm vi định danh** có thể tạo kết quả sai ngay cả khi cấu trúc bảng nhìn có vẻ hợp lý.

## 5. Ví dụ sai: thiếu thuộc tính để nối đúng

Xét quan hệ \(R(A,B,C)\), không có FD không tầm thường nào được bảo đảm. Trạng thái hợp lệ:

| A | B | C |
|---|---|---|
| a1 | b1 | c1 |
| a2 | b1 | c2 |

Phân rã thành:

~~~text
R1(A,B) = {(a1,b1), (a2,b1)}
R2(B,C) = {(b1,c1), (b1,c2)}
~~~

Giao là \(\{B\}\). Không có \(B\rightarrow A\) hay \(B\rightarrow C\), nên không có \(B\rightarrow AB\) hoặc \(B\rightarrow BC\).

Nối trên \(B\) cho:

~~~text
(a1, b1, c1)  -- gốc
(a1, b1, c2)  -- bộ giả
(a2, b1, c1)  -- bộ giả
(a2, b1, c2)  -- gốc
~~~

Đây là **phản ví dụ hợp lệ** chứng minh phân rã không lossless theo tập FD rỗng.

Một quan sát quan trọng: việc cả hai bảng con đều chứa `B` **không đủ**. Phải có ràng buộc nghiệp vụ đảm bảo các thuộc tính chung xác định một phía, hoặc một ràng buộc tổng quát hơn như MVD/JD.

## 6. Phân rã chỉ chứa một phần cột là vấn đề khác

Cho \(R(A,B,C)\), nếu chỉ giữ `R1(A,B)` rồi bỏ `C` mà không có bảng khác chứa `C`, đó **không phải** một phân rã đầy đủ của \(R\), vì:

\[
U_1\ne U.
\]

Không thể khôi phục giá trị \(C\) bằng cách nối khi thuộc tính này không xuất hiện ở bất kỳ quan hệ con nào. Trước khi thử tiêu chí giao, phải kiểm tra:

\[
\bigcup_i U_i=U.
\]

Đây là bước sơ bộ thường bị bỏ quên khi viết thuật toán tổng hợp 3NF từ các phụ thuộc hàm.

## 7. Phân rã thành ba bảng trở lên: kiểm tra theo chuỗi

Với nhiều quan hệ con \(R_1,R_2,\ldots,R_n\), không thể chỉ thấy các cặp bảng có chung một cột rồi kết luận **cả phép nối** khôi phục đúng dữ liệu. Một cách chứng minh dễ thực hành là xây dựng **chuỗi phân rã nhị phân lossless**.

### Ví dụ phân rã ba bảng có chứng minh

Xét:

\[
R(A,B,C,D)
\]

với:

~~~text
F = {
    A → B,
    B → C,
    C → D
}
~~~

Ta muốn tạo ba quan hệ:

~~~text
R1(A,B)
R2(B,C)
R3(C,D)
~~~

Thay vì kiểm tra rời rạc từng cặp, ta chứng minh:

**Bước 1:** Tách \(R(A,B,C,D)\) thành \(T(A,B,C)\) và \(R_3(C,D)\).

Giao là \(\{C\}\). Vì \(C\rightarrow D\), có \(C\rightarrow CD\). Do đó bước này **lossless** theo \(F\).

**Bước 2:** Tiếp tục tách \(T(A,B,C)\) thành \(R_1(A,B)\) và \(R_2(B,C)\).

Giao là \(\{B\}\). Vì \(B\rightarrow C\), có \(B\rightarrow BC\). Bước này cũng **lossless**.

Kết hợp:

\[
r=\pi_{ABC}(r)\bowtie\pi_{CD}(r)
=\pi_{AB}(r)\bowtie\pi_{BC}(r)\bowtie\pi_{CD}(r).
\]

Vậy **toàn bộ phân rã ba bảng lossless**.

~~~mermaid
flowchart TD
  R["R(A,B,C,D)"] --> T["T(A,B,C)"]
  R --> R3["R3(C,D)"]
  T --> R1["R1(A,B)"]
  T --> R2["R2(B,C)"]
~~~

Sơ đồ thể hiện **hai bước phân rã**. Mỗi bước phải được chứng minh lossless bằng các phụ thuộc đúng trên quan hệ đang xét; khi đó toàn bộ chuỗi là lossless.

### Khi không tìm được chuỗi đơn giản

Một phân rã nhiều bảng vẫn có thể lossless bởi **JD nhiều phép chiếu**, dù ta không tìm ra cách chứng minh chỉ bằng điều kiện FD cho từng bước. Có thể sử dụng phương pháp **tableau/chase** với tập phụ thuộc đã biết. Không được lấy “không áp dụng được tiêu chí nhị phân FD” làm kết luận chắc chắn rằng mọi phép phân rã tổng quát đều lossy.

## 8. Phương pháp tableau/chase để kiểm tra lossless theo FD

**Chase** là phương pháp suy luận có hệ thống, đặc biệt hữu ích khi số quan hệ con lớn và việc chứng minh bằng mắt khó kiểm soát. Dưới đây là bản cơ bản dùng **phụ thuộc hàm**.

### Ý tưởng lập bảng ký hiệu

Cho quan hệ gốc \(R(A_1,\ldots,A_m)\) và phép phân rã \(R_1,\ldots,R_n\):

1. Tạo **một dòng tableau cho mỗi quan hệ con**.
2. Với thuộc tính \(A_j\) **có trong** quan hệ con ở dòng \(i\), điền ký hiệu **phân biệt** \(a_j\).
3. Với thuộc tính \(A_j\) **không có trong** quan hệ con ở dòng \(i\), điền một ký hiệu riêng \(b_{ij}\).
4. Áp dụng các FD: nếu hai dòng bằng nhau trên toàn bộ vế trái \(X\), hợp nhất các ký hiệu tương ứng ở vế phải \(Y\); ưu tiên ký hiệu phân biệt \(a_j\) khi có.
5. Lặp đến khi không có thay đổi. Nếu có **một dòng toàn các ký hiệu \(a_j\)**, phép phân rã lossless theo các FD đang xét.

Với ràng buộc là **FD**, đây là tiêu chí kiểm tra tiêu chuẩn; nếu cần xét MVD/JD, phải dùng các quy tắc chase thích hợp cho loại phụ thuộc đó.

### Ví dụ chase: \(R(A,B,C)\rightarrow R_1(A,B),R_2(A,C)\)

Cho \(F=\{A\rightarrow B\}\). Tableau ban đầu:

| Dòng | A | B | C |
|---|---|---|---|
| \(R_1(A,B)\) | \(a_A\) | \(a_B\) | \(b_{1C}\) |
| \(R_2(A,C)\) | \(a_A\) | \(b_{2B}\) | \(a_C\) |

Hai dòng đều có cùng giá trị \(a_A\) ở cột \(A\). Theo \(A\rightarrow B\), cột \(B\) phải bằng nhau. Ta thay \(b_{2B}\) bằng \(a_B\):

| Dòng | A | B | C |
|---|---|---|---|
| \(R_1(A,B)\) | \(a_A\) | \(a_B\) | \(b_{1C}\) |
| \(R_2(A,C)\) | \(a_A\) | \(a_B\) | \(a_C\) |

Dòng \(R_2\) giờ gồm toàn ký hiệu phân biệt \((a_A,a_B,a_C)\). Vì vậy phân rã **lossless** theo \(A\rightarrow B\).

Nếu bỏ FD `A → B` và không có ràng buộc liên quan khác, các ký hiệu không được hợp nhất; không có dòng toàn ký hiệu phân biệt. Điều đó phù hợp với khả năng xuất hiện bộ giả khi nối hai phép chiếu.

### Lưu ý khi dùng chase

- Không tùy tiện đổi hai ký hiệu thành giống nhau nếu không có phụ thuộc hợp lệ làm cơ sở.
- Kết quả phụ thuộc vào **tập ràng buộc nhập vào**, không phải số dòng dữ liệu mẫu.
- Với nhiều loại phụ thuộc, chase tổng quát có thể phức tạp; nên dùng công cụ/thuật toán phù hợp với FD, MVD hoặc JD đang xét.
- Mục tiêu là **chứng minh về mọi trạng thái hợp lệ**, thay vì chỉ chạy thử `JOIN` trên một bản export.

## 9. Mối liên hệ với MVD và JD

### Phụ thuộc đa trị có thể bảo đảm lossless mà không cần FD

Cho:

~~~text
EMPLOYEE_PROFILE(employee_id, skill, language)
~~~

Nếu nghiệp vụ xác nhận **mỗi nhân viên có hai danh sách kỹ năng và ngôn ngữ độc lập**, ta có:

\[
\text{employee\_id}\twoheadrightarrow\text{skill}.
\]

Khi đó phân rã:

~~~text
EMPLOYEE_SKILLS(employee_id, skill)
EMPLOYEE_LANGUAGES(employee_id, language)
~~~

là **lossless theo MVD**, ngay cả khi `employee_id` **không xác định duy nhất** `skill` hoặc `language`. Điều kiện giao xác định một trong hai quan hệ con bằng FD **không thỏa**, nhưng phân rã vẫn lossless nhờ tính độc lập đa trị.

Đây là ví dụ cho thấy tiêu chí FD ở phần 3 **không bao trùm mọi loại ràng buộc dữ liệu**.

### Phụ thuộc nối tổng quát

Một **join dependency**:

\[
*\{U_1,U_2,\ldots,U_n\}
\]

khẳng định rằng mọi trạng thái hợp lệ đều bằng phép nối các phép chiếu lên \(U_1,\ldots,U_n\). Chính phát biểu này là bảo đảm lossless cho phép phân rã tương ứng.

Với `SUPPLY(supplier_id,part_id,project_id)`, nếu quyền cung cấp bộ ba được định nghĩa **chỉ bởi** ba phê duyệt cặp:

~~~text
(supplier_id, part_id)
(supplier_id, project_id)
(part_id, project_id)
~~~

thì JD trên ba phép chiếu có thể đúng. Nếu bảng gốc lưu **hợp đồng cung cấp thực tế**, ba phê duyệt cặp không đủ xác định bộ ba hợp đồng, và phép nối có thể sinh **hợp đồng giả**.

Vì thế, không suy JD chỉ từ việc có các quan hệ cặp, cũng không tách ba ngôi thành ba bảng cặp khi chưa có quy tắc nghiệp vụ xác nhận **mọi bộ ba hợp lệ được quyết định hoàn toàn bởi các cặp**.

## 10. Lossless khác bảo toàn phụ thuộc

Hai tiêu chí phục vụ hai mục tiêu khác nhau:

| Tiêu chí | Câu hỏi | Nếu không đạt |
|---|---|---|
| **Nối không mất mát** | Chiếu ra rồi nối lại có khôi phục **đúng các bộ gốc** không? | Có thể sinh bộ giả, làm sai câu trả lời truy vấn |
| **Bảo toàn phụ thuộc** | Có thể suy ra **tất cả các FD gốc** từ các FD kiểm soát riêng trong từng bảng con không? | Một số quy tắc phải kiểm tra qua nhiều bảng hoặc bằng cơ chế khác |

Với các FD \(F\) và các quan hệ con \(R_i\), bảo toàn phụ thuộc có thể phát biểu:

\[
\left(\bigcup_i \pi_{R_i}(F)\right)^+=F^+,
\]

trong đó \(\pi_{R_i}(F)\) là tập các FD trong \(F^+\) **chỉ dùng thuộc tính của \(R_i\)**. Đây là phép chiếu **tập phụ thuộc**, khác với phép chiếu dữ liệu.

### Ví dụ lossless nhưng không bảo toàn FD

Xét \(R(A,B,C)\) với:

~~~text
F = {
    AB → C,
    C  → B
}
~~~

Phân rã:

~~~text
R1(C,B)
R2(A,C)
~~~

Giao là \(\{C\}\). Vì \(C\rightarrow B\), \(\{C\}\rightarrow\{B,C\}=U_1\). Vậy phân rã **lossless**.

Nhưng `AB → C` không được bảo toàn bằng các FD cục bộ:

~~~text
R1(C,B) = {(c1,b1), (c2,b1)}
R2(A,C) = {(a1,c1), (a1,c2)}
~~~

Mỗi bảng con có thể thỏa các ràng buộc cục bộ. Khi nối, ta có:

~~~text
(a1,b1,c1)
(a1,b1,c2)
~~~

Hai bộ cùng `(A,B)` nhưng khác `C` vi phạm `AB → C`. Điều đó chứng minh chỉ kiểm soát từng bảng con **không đủ** để bảo đảm FD gốc.

### Hệ quả khi chuẩn hóa

- Thuật toán **tổng hợp 3NF** chuẩn có thể tạo phân rã vừa **nối không mất mát** vừa **bảo toàn các FD** đầu vào.
- Thuật toán phân rã theo **BCNF** bằng các bước nhị phân được chọn đúng có thể bảo đảm **nối không mất mát**, nhưng **không luôn bảo toàn tất cả FD**.
- Phân rã theo MVD để đạt **4NF** phải được kiểm tra lossless theo phụ thuộc đa trị thực sự đúng. Những ràng buộc liên quan đến bộ ba/hợp đồng có thể cần xét **JD** và **5NF**.

Đây là những **thuộc tính của thuật toán và ràng buộc cụ thể**, không phải lời hứa rằng chỉ cần bảng con đạt một dạng chuẩn cao thì mọi quy tắc nghiệp vụ đã tự được giữ.

## 11. Kiểm tra phản ví dụ bằng SQL

SQL giúp phát hiện bộ giả trên **trạng thái dữ liệu hiện có**. Tuy nhiên nó không tự chứng minh một phép phân rã lossless cho **mọi trạng thái hợp lệ**.

Giả sử `staging_student_tutor(student_id, course_id, tutor_id)` lưu các **phân công thực tế**. Ta muốn thử phép tách thành `(student_id, course_id)` và `(course_id, tutor_id)`.

~~~sql
WITH original AS (
    SELECT DISTINCT student_id, course_id, tutor_id
    FROM staging_student_tutor
    WHERE student_id IS NOT NULL
      AND course_id IS NOT NULL
      AND tutor_id IS NOT NULL
),
student_course AS (
    SELECT DISTINCT student_id, course_id
    FROM original
),
course_tutor AS (
    SELECT DISTINCT course_id, tutor_id
    FROM original
),
reconstructed AS (
    SELECT sc.student_id, sc.course_id, ct.tutor_id
    FROM student_course AS sc
    JOIN course_tutor AS ct
      ON ct.course_id = sc.course_id
),
spurious AS (
    SELECT student_id, course_id, tutor_id FROM reconstructed
    EXCEPT
    SELECT student_id, course_id, tutor_id FROM original
)
SELECT *
FROM spurious
ORDER BY course_id, student_id, tutor_id;
~~~

Với dữ liệu hai dòng ở phần đầu, truy vấn trả về:

~~~text
SV01 | C01 | GV02
SV02 | C01 | GV01
~~~

Đây là hai bộ có trong kết quả nối nhưng không có trong bản gốc. Trên dữ liệu này, phép phân rã đã tạo **bộ giả**. Nếu đó là một trạng thái **nghiệp vụ hợp lệ**, nó bác bỏ đề xuất phân rã lossless.

### Vì sao truy vấn không trả dòng nào vẫn chưa đủ?

Một mẫu chỉ có **một gia sư trên mỗi môn** có thể khiến phép nối tình cờ tái tạo đúng, kể cả khi nghiệp vụ về sau cho phép nhiều gia sư. Muốn chứng minh lossless cần một trong những căn cứ:

1. **FD** phù hợp với tiêu chí phân rã hai quan hệ.
2. **MVD hoặc JD** đã xác nhận nếu dựa vào tính độc lập nhiều giá trị.
3. **Chứng minh từng bước hoặc chase** cho phân rã phức tạp.

Không kết luận từ một lần `EXCEPT` không có kết quả.

### Lưu ý khác nhau giữa lý thuyết quan hệ và SQL

- Mô hình quan hệ lý thuyết dùng **tập hợp**: một bộ không xuất hiện hai lần. SQL thường dùng **đa tập** (*bag semantics*). Vì vậy ví dụ dùng `SELECT DISTINCT` và `EXCEPT` để so sánh **tập giá trị bộ**.
- Các truy vấn đang loại hàng có `NULL`; cần xử lý dữ liệu thiếu riêng, bởi quy tắc `NULL` trong SQL có thể khiến `JOIN` hoặc phép đếm không phản ánh đầy đủ ý nghĩa nghiệp vụ.
- Trong các hệ quản trị khác nhau, cú pháp phép trừ tập hợp có thể là `EXCEPT` hoặc `MINUS`. Hãy điều chỉnh theo DBMS đang dùng.
- Nếu các bảng con được tạo bằng **quy trình cập nhật riêng**, việc chúng từng là phép chiếu của cùng một bản gốc không đảm bảo chúng luôn đồng bộ về sau. Cần thêm khóa ngoại, giao dịch và cơ chế nhất quán.

## 12. Từ chứng minh lossless đến lược đồ vật lý

Khi các quy tắc:

~~~text
order_id            → customer_id
(order_id, line_no) → product_id, quantity
~~~

đã được nghiệp vụ xác nhận, có thể triển khai:

~~~sql
CREATE TABLE customers (
    customer_id VARCHAR(30) PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);

CREATE TABLE products (
    product_id VARCHAR(30) PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id VARCHAR(30) PRIMARY KEY,
    customer_id VARCHAR(30) NOT NULL REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_id VARCHAR(30) NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id VARCHAR(30) NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Ở mức logic, phân rã gốc `ORDER_LINE_FLAT` thành `ORDERS` và `ORDER_ITEMS` lossless theo `order_id → customer_id`. Khi triển khai:

- `orders.order_id` là **khóa chính**, bảo đảm mỗi đơn có một dòng thông tin đơn.
- `order_items(order_id,line_no)` là **khóa chính ghép**, biểu diễn mỗi số dòng duy nhất trong đơn.
- Khóa ngoại `order_items.order_id → orders.order_id` ngăn tạo dòng hàng cho đơn không tồn tại.
- `quantity > 0` là **ràng buộc miền giá trị**, không suy ra từ FD.
- Nếu cần tốc độ truy vấn danh sách đơn theo khách, có thể xem xét chỉ mục trên `orders.customer_id` theo workload.

Một phép nối để khôi phục bảng chi tiết:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    i.line_no,
    i.product_id,
    i.quantity
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id;
~~~

Tuy nhiên **bảng con tồn tại độc lập** tạo ra những trạng thái mới không có trong bảng gộp cũ, ví dụ một đơn chưa có dòng hàng. `INNER JOIN` trên sẽ không trả đơn ấy. Điều này **không phủ định** chứng minh lossless của phép chiếu từ `ORDER_LINE_FLAT`: thuộc tính lossless chỉ nói về **khả năng khôi phục đúng một quan hệ gốc từ các phép chiếu của chính nó**. Thiết kế thực tế cần quyết định có cho phép đơn rỗng hay không và cách lưu, truy vấn các thực thể độc lập.

### Phân rã lossless chưa đủ bảo đảm chất lượng triển khai

Vẫn cần:

- Xác nhận **phạm vi định danh**: mã đơn duy nhất toàn cục hay theo cửa hàng/tenant.
- Thiết kế quy tắc **đổi khách hàng, xóa đơn, hoàn đơn và lịch sử** nếu có.
- Kiểm soát **khóa ngoại, NOT NULL, UNIQUE, CHECK** và giao dịch khi ghi nhiều bảng.
- Đo chi phí `JOIN` và lựa chọn chỉ mục phù hợp.
- Nếu tạo dữ liệu tổng hợp/materialized view, có quy tắc cập nhật và tránh nguồn dữ liệu không nhất quán.

**Lossless là điều kiện đúng đắn của mô hình quan hệ; nó không tự quyết định hiệu năng hay toàn bộ chính sách nghiệp vụ.**

## 13. Phương pháp thực hành để kiểm tra một đề xuất phân rã

Một quy trình phù hợp khi chuyển yêu cầu nghiệp vụ thành thiết kế:

### Bước 1 — Xác định mức hạt và tập thuộc tính

Viết rõ mỗi dòng của bảng gốc là **một đối tượng, một liên kết hay một sự kiện**. Kiểm tra tất cả thuộc tính của bảng gốc đều có trong ít nhất một quan hệ con:

\[
\bigcup_i U_i=U.
\]

### Bước 2 — Xác nhận phụ thuộc từ nghiệp vụ

Ghi các FD/MVD/JD đúng với phạm vi và thời gian hiệu lực. **Không** suy rằng một mã đang duy nhất trên mẫu nhỏ thì nó luôn là khóa. Nếu quy tắc chưa được xác nhận, đánh dấu giả định và hỏi người sở hữu nghiệp vụ.

### Bước 3 — Kiểm tra từng phép phân rã hai bảng

Tính giao \(I=U_1\cap U_2\), tính \(I_F^+\). Nếu \(U_1\subseteq I_F^+\) hoặc \(U_2\subseteq I_F^+\), bước phân rã lossless theo FD.

### Bước 4 — Với nhiều bảng, chứng minh toàn bộ phép nối

Tìm một chuỗi bước nhị phân lossless hoặc dùng chase/JD phù hợp. Không chỉ kiểm tra từng cặp bảng con riêng lẻ và bỏ qua quan hệ trung gian.

### Bước 5 — Kiểm tra bảo toàn phụ thuộc và dạng chuẩn

Đánh giá FD gốc có được giữ qua các quan hệ con không; xem các bảng có đáp ứng 3NF, BCNF, 4NF hay không theo loại phụ thuộc thực tế. Tính lossless và bảo toàn phụ thuộc là **hai tiêu chí riêng**.

### Bước 6 — Thử phản ví dụ và nghiệm thu vật lý

Dùng SQL tìm bộ giả trên dữ liệu staging; thêm các trường hợp khó như nhiều giá trị cùng khóa nối, dữ liệu theo nhiều tenant, dữ liệu lịch sử, các liên kết bị thiếu, `NULL` và nguồn độc lập. Cuối cùng bổ sung khóa, ràng buộc tham chiếu, chỉ mục và quy trình cập nhật phù hợp.

## 14. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
|---|---|---|
| “Hai bảng có cột chung nên join sẽ đúng” | Cột chung có thể không xác định duy nhất một bên | Kiểm tra `(R1∩R2) → R1` hoặc `→ R2` theo FD |
| “Có nhiều bảng thì kiểm tra từng cặp bất kỳ là đủ” | Phép nối toàn bộ có thể sinh tổ hợp giả ở bước sau | Chứng minh **chuỗi phân rã** hoặc dùng chase/JD |
| “Chạy JOIN trên dữ liệu mẫu không ra dòng giả là đã chứng minh” | Mẫu có thể thiếu trường hợp nghiệp vụ hợp lệ | Chứng minh với **mọi trạng thái hợp lệ** |
| “Không thỏa tiêu chí FD thì chắc chắn không lossless” | MVD/JD có thể bảo đảm lossless mà không có FD tương ứng | Kiểm tra đúng **loại phụ thuộc** |
| “Lossless tức là bảo toàn mọi phụ thuộc” | Có thể còn FD chỉ kiểm tra được qua nhiều bảng | Kiểm tra bảo toàn phụ thuộc riêng |
| “Chỉ cần thêm khóa ngoại là đủ” | Khóa ngoại kiểm tra tồn tại tham chiếu, không chứng minh mọi tổ hợp join là bộ thật | Xác định khóa và phụ thuộc nghiệp vụ, đánh giá bộ giả |
| “Bảng đạt BCNF/4NF thì tự động khôi phục đúng dữ liệu” | Dạng chuẩn của từng bảng không thay thế chứng minh phân rã | Kiểm tra điều kiện lossless của **phép tách** |
| “Dùng INNER JOIN không thấy đơn rỗng nên phân rã lossy” | Bảng sau triển khai có thể chứa trạng thái mới khác phép chiếu từ bảng gộp | Phân biệt **lossless của phép chiếu** và **ngữ nghĩa lưu trữ thực thể độc lập** |

## 15. Khi chọn mô hình quan hệ, document, đồ thị và phân tích

| Mô hình | Liên hệ tới khôi phục đúng dữ liệu | Điều cần kiểm tra |
|---|---|---|
| **Quan hệ** | Phân rã thành bảng con và join theo khóa | FD/MVD/JD, lossless, bảo toàn phụ thuộc, khóa ngoại |
| **Document** | Tách hoặc nhúng các nhóm thuộc tính trong document | ID tham chiếu, đồng bộ dữ liệu nhúng, ảnh chụp lịch sử |
| **Đồ thị** | Diễn đạt đối tượng và liên kết bằng node/edge | Không suy **quan hệ ba ngôi** chỉ từ ba quan hệ cặp |
| **Phân tích** | Join fact–dimension và các bridge theo mức hạt | Tránh nhân bản phép đo hoặc sinh tổ hợp giả khi join nhiều-nhiều |

Ví dụ, trong mô hình đồ thị, có cạnh sinh viên–môn và môn–gia sư **không chứng minh** gia sư đó đã kèm sinh viên. Trong mô hình phân tích, nếu nối một fact đơn hàng với hai bảng nhiều-nhiều mà chưa xác định mức hạt, `SUM(revenue)` có thể bị nhân nhiều lần. Bài học về **khôi phục đúng kết hợp dữ liệu** vẫn quan trọng dù cơ chế lưu trữ khác mô hình quan hệ cổ điển.

## 16. Bài luyện tập có lời giải

### Bài 1 — Kiểm tra điều kiện giao

Cho \(R(A,B,C,D)\) với \(F=\{A\rightarrow B,\ B\rightarrow C\}\). Phân rã `R1(A,B,C)`, `R2(A,D)` có lossless theo \(F\) không?

**Lời giải:** Giao là \(\{A\}\). Từ `A → B` và `B → C`, suy ra \(\{A\}^+=\{A,B,C\}\), xác định toàn bộ `R1(A,B,C)`. Vậy phân rã **lossless**.

### Bài 2 — Phân rã lossy

Cho \(R(A,B,C)\), \(F=\varnothing\) và các bộ `(a1,b1,c1)`, `(a2,b1,c2)\). Tách thành `R1(A,B)` và `R2(B,C)`. Phép nối tạo bộ nào không có trong \(R\)?

**Lời giải:** Hai bộ giả là `(a1,b1,c2)` và `(a2,b1,c1)`. Giao \(\{B\}\) không xác định được `A` hay `C`; phép phân rã **không lossless**.

### Bài 3 — Chuỗi phân rã ba bảng

Cho \(R(A,B,C,D)\), \(F=\{A\rightarrow B,\ B\rightarrow C,\ C\rightarrow D\}\). Chứng minh `{AB,BC,CD}` là phân rã lossless.

**Lời giải:** Tách `ABCD` thành `ABC` và `CD`: giao `C`, `C→D`, nên lossless. Tiếp tục tách `ABC` thành `AB` và `BC`: giao `B`, `B→C`, nên lossless. Hợp hai bước suy ra phân rã cuối cùng **lossless**.

### Bài 4 — Có lossless khi FD không đủ không?

Quan hệ `R(employee_id,skill,language)` lưu hai danh sách độc lập. Một nhân viên có nhiều kỹ năng và ngôn ngữ, không có `employee_id → skill` hoặc `employee_id → language`. Tách thành `(employee_id,skill)` và `(employee_id,language)` có lossless không?

**Lời giải:** Có **nếu** nghiệp vụ thật sự bảo đảm `employee_id ↠ skill`, vì đó là MVD tương đương JD hai phép chiếu. Tiêu chí nhị phân theo **FD** không áp dụng để bác bỏ phân rã này. Nếu kỹ năng và ngôn ngữ thực tế liên hệ theo từng cặp, phân rã sẽ sinh bộ giả.

### Bài 5 — Lossless khác bảo toàn phụ thuộc

Cho \(R(A,B,C)\), \(F=\{AB\rightarrow C,\ C\rightarrow B\}\). Tách thành `R1(C,B)`, `R2(A,C)`.

**Lời giải:** Giao \(\{C\}\) xác định `R1(C,B)`, nên **lossless**. Nhưng `AB→C` không được bảo toàn bởi FD cục bộ: hai bảng con có thể cho phép cùng cặp `AB` ghép với hai giá trị `C` khác nhau.

### Bài 6 — Khóa thiếu phạm vi

Trong một nền tảng đa cửa hàng, số đơn `order_no` chỉ duy nhất **trong mỗi cửa hàng**. Có nên tách `ORDER_LINE(store_id,order_no,line_no,customer_id,product_id)` thành bảng đơn chứa `order_no,customer_id` và bảng dòng chứa `order_no,line_no,product_id`, rồi nối trên `order_no` không?

**Lời giải:** Không, vì hai cửa hàng có thể trùng `order_no` với khách và sản phẩm khác nhau, dẫn đến nối nhầm. Cần xác nhận khóa theo phạm vi, ví dụ `(store_id,order_no)`, rồi đưa **cùng khóa này** vào hai bảng con và điều kiện nối.

### Bài 7 — Một đơn chưa có dòng hàng

Sau khi tách `ORDERS` và `ORDER_ITEMS`, một đơn `DH99` được tạo nhưng chưa có dòng hàng. Truy vấn `INNER JOIN` không trả đơn này. Có thể kết luận phân rã đã sai tính lossless không?

**Lời giải:** Không thể kết luận như vậy. **Lossless** được định nghĩa với phép chiếu từ **cùng một quan hệ gốc**. Đơn chưa có dòng hàng là trạng thái bổ sung mà thiết kế hai thực thể cho phép biểu diễn. Nếu nghiệp vụ cần xem đơn rỗng, truy vấn trực tiếp `ORDERS` hoặc dùng `LEFT JOIN`. Nếu nghiệp vụ **cấm** đơn rỗng, cần quy tắc kiểm soát tương ứng.

## 17. Checklist trước khi chốt phân rã

- [ ] Đã xác định mức hạt và ý nghĩa nghiệp vụ của mỗi dòng.
- [ ] Tập các quan hệ con bao phủ toàn bộ thuộc tính gốc.
- [ ] Đã xác nhận FD/MVD/JD và phạm vi định danh, thời gian hiệu lực.
- [ ] Với hai bảng theo FD, đã tính giao và bao đóng để kiểm tra tiêu chí lossless.
- [ ] Với nhiều bảng, đã chứng minh một **chuỗi lossless** hoặc dùng chase/JD phù hợp.
- [ ] Đã thử phản ví dụ có nhiều dòng cùng khóa nối để tìm bộ giả.
- [ ] Đã kiểm tra **bảo toàn phụ thuộc** riêng với tính nối không mất mát.
- [ ] Đã phân biệt việc chiếu từ một quan hệ với lưu hai bảng độc lập sau triển khai.
- [ ] Đã xem xét `NULL`, dữ liệu trùng, khóa ngoại và các giao dịch cập nhật.
- [ ] Đã đánh giá chi phí join, chỉ mục, khả năng tiến hóa lược đồ và workload thực tế.

**Ghi nhớ:** Một phân rã **nối không mất mát** khi mọi trạng thái dữ liệu hợp lệ đều được **khôi phục đúng bằng cách nối các phép chiếu**, không sinh bộ giả. Với hai bảng dựa trên FD, kiểm tra **giao các thuộc tính có xác định một bảng con hay không**. Với các phụ thuộc đa trị, phụ thuộc nối và nhiều bảng, phải dùng đúng lập luận tương ứng. Chứng minh **lossless** là bước bắt buộc trước khi chốt cấu trúc dữ liệu, và **bảo toàn phụ thuộc** cần được đánh giá riêng.

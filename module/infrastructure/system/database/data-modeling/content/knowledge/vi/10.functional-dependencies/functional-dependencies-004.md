# Phủ tối thiểu và vai trò khi phân rã lược đồ

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, mục tiêu không chỉ là vẽ thực thể và quan hệ, mà còn là biến quy tắc nghiệp vụ thành **khóa, ràng buộc, bảng và lược đồ vật lý** có thể kiểm chứng. **Phủ tối thiểu** (*minimal cover*, thường gọi là *canonical cover* với một số khác biệt về cách trình bày) giúp rút gọn tập phụ thuộc hàm nhưng vẫn giữ nguyên những điều dữ liệu bắt buộc phải tuân thủ. Nó đặc biệt hữu ích khi phân tích chuẩn hóa và tổng hợp lược đồ đạt dạng chuẩn ba (3NF).

Sau bài này, bạn có thể:

- Giải thích **tương đương của hai tập phụ thuộc hàm** và định nghĩa phủ tối thiểu.
- Tính bao đóng thuộc tính để phát hiện **thuộc tính thừa ở vế trái**, **thuộc tính dư ở vế phải** và **phụ thuộc hàm dư thừa**.
- Từng bước xây dựng một phủ tối thiểu, rồi chứng minh tập kết quả **tương đương** với đầu vào.
- Dùng phủ tối thiểu trong **thuật toán tổng hợp lược đồ 3NF**.
- Phân biệt hai tiêu chí phải kiểm tra khi phân rã: **nối không mất mát** và **bảo toàn phụ thuộc**; hiểu đánh đổi thường gặp với BCNF.

## 1. Bối cảnh: nhiều phụ thuộc có thể chỉ nói cùng một sự thật

Xét quan hệ:

\[
R(A,B,C,D,E)
\]

với tập phụ thuộc hàm \(F\):

~~~text
F = {
    A  → BC,
    B  → C,
    AC → D,
    D  → E,
    A  → E
}
~~~

Ký hiệu `A → BC` nghĩa là mỗi giá trị `A` xác định đồng thời `B` và `C`; `AC → D` nghĩa là **cặp** `(A,C)` xác định `D`.

Trong tập trên có những điều đã được quy tắc khác bảo đảm:

- `A → C` đã suy ra từ `A → B` và `B → C`.
- Trong `AC → D`, `C` không thực sự cần có ở vế trái, vì từ `A` suy ra `C`, rồi dùng `AC → D` để suy ra `D`.
- `A → E` có thể suy ra qua `A → D` và `D → E` sau bước rút gọn trên.

Vì vậy ta có thể diễn đạt cùng các ràng buộc bằng một tập ngắn gọn hơn:

~~~text
G = {
    A → B,
    B → C,
    A → D,
    D → E
}
~~~

**Câu hỏi quan trọng:** Làm sao biết \(G\) vẫn giữ nguyên toàn bộ quy tắc trong \(F\), thay vì vô tình xóa một ràng buộc nghiệp vụ? Ta cần dùng định nghĩa tương đương và phép tính bao đóng, không chỉ dựa vào trực giác.

## 2. Nền tảng: phụ thuộc suy ra, bao đóng và tính tương đương

Với lược đồ quan hệ \(R(U)\), phụ thuộc \(X\rightarrow Y\) đúng khi trong **mọi trạng thái dữ liệu hợp lệ**, hai dòng bằng nhau trên tập thuộc tính \(X\) phải bằng nhau trên tập \(Y\).

Tập \(F^+\) là **tất cả phụ thuộc hàm suy ra được từ \(F\)** theo các quy tắc Armstrong. Bao đóng \(X_F^+\) là **tập thuộc tính có thể suy ra từ \(X\)** dựa trên \(F\):

\[
X_F^+=\{A\in U\mid F\models X\rightarrow A\}.
\]

Muốn biết \(F\models X\rightarrow Y\), chỉ cần kiểm tra:

\[
Y\subseteq X_F^+.
\]

### Thuật toán bao đóng thuộc tính

~~~text
ATTRIBUTE_CLOSURE(X, F):
    result := X
    repeat:
        previous := result
        for each dependency L → T in F:
            if L ⊆ result:
                result := result ∪ T
    until result = previous
    return result
~~~

Thuật toán liên tục thêm thuộc tính, không bao giờ xóa thuộc tính, và dừng khi không còn thay đổi. Vì tập thuộc tính hữu hạn, nó luôn dừng.

### Hai tập phụ thuộc tương đương

Hai tập \(F\) và \(G\) **tương đương** khi:

\[
F^+=G^+.
\]

Tương đương cũng có nghĩa: mọi phụ thuộc trong \(F\) suy ra được từ \(G\), **và ngược lại** mọi phụ thuộc trong \(G\) suy ra được từ \(F\).

Để kiểm tra mà không cần liệt kê \(F^+\) hoặc \(G^+\):

1. Với từng \(X\rightarrow Y\) trong \(F\), kiểm tra \(Y\subseteq X_G^+\).
2. Với từng \(X\rightarrow Y\) trong \(G\), kiểm tra \(Y\subseteq X_F^+\).
3. Chỉ khi **cả hai chiều** đều đúng, kết luận \(F^+=G^+\).

Chỉ kiểm tra một chiều có thể khiến ta **làm mất phụ thuộc** hoặc **thêm quy tắc mạnh hơn nghiệp vụ** mà không phát hiện.

## 3. Phủ tối thiểu là gì?

Một **phủ tối thiểu** thường được định nghĩa là tập phụ thuộc \(G\) thỏa các điều kiện:

1. **Tương đương:** \(G^+=F^+\).
2. **Vế phải đơn thuộc tính:** mỗi phụ thuộc trong \(G\) có dạng \(X\rightarrow A\), trong đó \(A\) là **một thuộc tính**.
3. **Không có thuộc tính thừa ở vế trái:** không thể bỏ một thuộc tính khỏi vế trái của bất kỳ phụ thuộc nào mà vẫn giữ tập tương đương.
4. **Không có phụ thuộc dư thừa:** không thể xóa hẳn một phụ thuộc khỏi \(G\) mà vẫn giữ tập tương đương.

Một số tài liệu gọi dạng đã **gộp các phụ thuộc cùng vế trái** là *canonical cover*; một số khác dùng hai tên thay thế nhau. Khi trao đổi hoặc viết bài thi, hãy nêu rõ quy ước **vế phải một thuộc tính hay được phép gộp**. Việc gộp `A → B` và `A → D` thành `A → BD` không thay đổi ý nghĩa phụ thuộc.

**Tối thiểu** ở đây là tối thiểu theo các phép loại bỏ dư thừa vừa nêu. Nó **không** nhất thiết là cách viết có ít ký tự nhất hoặc ít dòng nhất. Một tập phụ thuộc có thể có **nhiều phủ tối thiểu khác nhau** nhưng vẫn tương đương.

## 4. Ba thao tác rút gọn và cách kiểm chứng

### 4.1. Tách vế phải

Theo quy tắc phân rã của phụ thuộc hàm:

\[
X\rightarrow YZ \iff
(X\rightarrow Y)\land(X\rightarrow Z).
\]

Do đó:

~~~text
A → BC
~~~

được thay bằng:

~~~text
A → B
A → C
~~~

Đây là bước **chuẩn hóa cách biểu diễn**, chưa xóa nội dung nghiệp vụ.

### 4.2. Phát hiện thuộc tính thừa ở vế trái

Với một phụ thuộc \(XA\rightarrow B\), thuộc tính \(A\) **thừa ở vế trái** nếu từ phần còn lại \(X\) cũng suy ra được \(B\):

\[
B\in X_F^+.
\]

Khi đó có thể thay `XA → B` bằng `X → B` mà vẫn giữ tính tương đương.

Ví dụ với `AC → D` trong \(F\), muốn biết `C` có thừa không, tính `{A}+` bằng tập phụ thuộc hiện hành:

~~~text
Khởi đầu:       {A}
Nhờ A → B:      {A, B}
Nhờ B → C:      {A, B, C}
Nhờ AC → D:     {A, B, C, D}
Nhờ D → E:      {A, B, C, D, E}
~~~

Do `D ∈ {A}+`, ta có `A → D`. Vậy `C` thừa trong `AC → D`.

**Không nhầm với kiểm tra một phụ thuộc dư thừa.** Ở đây ta kiểm tra có thể **bớt một thuộc tính của vế trái**, chưa phải có thể xóa **toàn bộ phụ thuộc**. Phép bao đóng được tính trên **tập hiện hành** có chứa phụ thuộc đang rút gọn. Khi thay `AC → D` bằng `A → D`, chiều ngược `A → D ⇒ AC → D` đúng theo tiên đề tăng trưởng.

### 4.3. Xóa phụ thuộc hàm dư thừa

Với một phụ thuộc \(f=(X\rightarrow A)\) trong \(G\), chỉ được xóa \(f\) nếu:

\[
A\in X_{G-\{f\}}^+.
\]

Tức là **bỏ hẳn phụ thuộc đang kiểm tra**, rồi tính bao đóng chỉ từ các phụ thuộc **còn lại**.

Ví dụ, với:

~~~text
G = {
    A → B,
    B → C,
    A → D,
    D → E,
    A → E
}
~~~

Kiểm tra `A → E`: bỏ `A → E` khỏi tập; vẫn suy ra `A → D → E`, nên `A → E` **dư thừa** và được xóa.

Nếu tính `{A}+` **mà vẫn giữ** `A → E` khi kiểm tra chính phụ thuộc đó, việc tìm ra `E` là hiển nhiên và không chứng minh được gì. Đây là lỗi rất phổ biến trong bài làm phủ tối thiểu.

## 5. Ví dụ tính phủ tối thiểu đầy đủ

Quay lại:

~~~text
F = {
    A  → BC,
    B  → C,
    AC → D,
    D  → E,
    A  → E
}
~~~

### Bước 1 — Tách vế phải thành từng thuộc tính

~~~text
F1 = {
    A  → B,
    A  → C,
    B  → C,
    AC → D,
    D  → E,
    A  → E
}
~~~

### Bước 2 — Rút gọn vế trái

`AC → D` có vế trái ghép. Thử bỏ `C`:

- Từ `A` suy ra `B` nhờ `A → B`.
- Từ `B` suy ra `C` nhờ `B → C`.
- Khi có `A,C`, suy ra `D` nhờ `AC → D`.

Vậy `D ∈ {A}+`, thay `AC → D` bằng `A → D`:

~~~text
F2 = {
    A → B,
    A → C,
    B → C,
    A → D,
    D → E,
    A → E
}
~~~

### Bước 3 — Xóa từng phụ thuộc dư thừa

Kiểm tra `A → C`: nếu bỏ phụ thuộc này, từ `A → B` và `B → C` vẫn suy ra `A → C`. Xóa được.

Kiểm tra `A → E`: nếu bỏ phụ thuộc này, từ `A → D` và `D → E` vẫn suy ra `A → E`. Xóa được.

Kết quả:

~~~text
G = {
    A → B,
    B → C,
    A → D,
    D → E
}
~~~

Không phụ thuộc nào trong \(G\) có thể bị xóa mà vẫn suy ra được chính nó từ ba phụ thuộc còn lại. Vế trái đều chỉ gồm một thuộc tính và không có thuộc tính thừa (theo các quy tắc đang xét, không có phụ thuộc từ tập rỗng tới các thuộc tính vế phải).

### Bước 4 — Chứng minh \(F\) và \(G\) tương đương

**Chiều \(G\models F\):** với tập \(G\), kiểm tra tất cả các phụ thuộc gốc:

| Phụ thuộc trong \(F\) | Cách suy ra từ \(G\) |
|---|---|
| `A → BC` | `A → B`; rồi `B → C`; hợp lại được `A → BC` |
| `B → C` | Có sẵn |
| `AC → D` | `A → D`; thêm `C` vào vế trái không làm mất phụ thuộc |
| `D → E` | Có sẵn |
| `A → E` | `A → D → E` |

**Chiều \(F\models G\):**

| Phụ thuộc trong \(G\) | Cách suy ra từ \(F\) |
|---|---|
| `A → B` | Phân rã từ `A → BC` |
| `B → C` | Có sẵn |
| `A → D` | `A → C` từ `A → BC`; kết hợp `AC → D` |
| `D → E` | Có sẵn |

Do suy diễn được theo **cả hai chiều**, \(F^+=G^+\). Đây là điều phải giữ nguyên khi chuyển từ mô tả nghiệp vụ sang một tập ràng buộc gọn hơn.

## 6. Thuật toán tìm phủ tối thiểu

Một cách triển khai dễ kiểm tra:

~~~text
MINIMAL_COVER(F):
    G := split_every_rhs_into_single_attributes(F)

    # Rút gọn vế trái; thay từng phụ thuộc bằng dạng rút gọn.
    for each dependency (X → A) in G:
        for each attribute b in X:
            if A ∈ ATTRIBUTE_CLOSURE(X - {b}, G):
                replace (X → A) in G with ((X - {b}) → A)
                X := X - {b}

    # Xóa phụ thuộc dư thừa; có thể lặp đến khi ổn định.
    for each dependency f = (X → A) in a copy of G:
        if A ∈ ATTRIBUTE_CLOSURE(X, G - {f}):
            remove f from G

    return G
~~~

**Lưu ý cách áp dụng:**

- Sau mỗi lần rút gọn hoặc xóa, tính bao đóng bằng **tập \(G\) mới nhất**.
- Ở bước kiểm tra vế trái, có thể dùng tập đang chứa phụ thuộc; ở bước **xóa cả phụ thuộc**, bắt buộc dùng `G - {f}`.
- Việc rút gọn có thể ảnh hưởng cách phát hiện các thuộc tính thừa khác; cài đặt tổng quát nên tiếp tục quét cho đến khi không còn thay đổi và có thể xác minh tính tương đương sau cùng.
- Nếu một vế trái trở thành **tập rỗng**, phụ thuộc \(\varnothing\rightarrow A\) có nghĩa \(A\) có cùng giá trị trong mọi dòng hợp lệ. Đó là trường hợp biên hợp lệ về lý thuyết; đừng tự động loại bỏ vì thấy lạ.
- Kết quả có thể thay đổi theo thứ tự xét các phụ thuộc nhưng các phủ tối thiểu hợp lệ phải **tương đương** với \(F\).

Đối với mô hình nhiều thuộc tính và nhiều phụ thuộc, phép tính bao đóng thường dễ tự động hóa hơn việc tự liệt kê toàn bộ \(F^+\). Tuy nhiên, **phủ tối thiểu không xác nhận tính đúng của quy tắc đầu vào**: nếu \(F\) suy ra từ một giả định sai, đầu ra tương đương vẫn phản ánh chính sai lầm đó.

## 7. Vai trò của phủ tối thiểu khi phân rã lược đồ

Một bảng gộp có thể chứa thông tin ở nhiều cấp: thông tin đơn hàng, khách hàng, sản phẩm và từng dòng hàng. Phụ thuộc hàm cho biết thuộc tính nào phải nằm cùng một khóa định danh; chuẩn hóa dùng thông tin đó để giảm **bất thường cập nhật, chèn và xóa**.

Phủ tối thiểu hỗ trợ ba việc:

1. **Làm rõ các phụ thuộc thực sự cần biểu diễn:** tránh xử lý lặp những quy tắc vốn là hệ quả của quy tắc khác.
2. **Định hướng nhóm thuộc tính có cùng vế trái:** ví dụ `A → B` và `A → D` có thể được nhóm thành `A → BD` để tạo một lược đồ chứa `A,B,D`.
3. **Dẫn đường cho thuật toán tổng hợp 3NF:** tạo các quan hệ từ phủ tối thiểu, rồi bảo đảm nối không mất mát và bảo toàn phụ thuộc.

Nhưng cần phân biệt: **rút gọn tập phụ thuộc** là thao tác logic trên \(F\); **phân rã lược đồ** là thao tác trên tập cột \(U\). Một tập phụ thuộc gọn hơn **chưa tự động** tạo ra bộ bảng đúng. Cần kiểm tra các tính chất của phép phân rã.

## 8. Hai tiêu chí bắt buộc: nối không mất mát và bảo toàn phụ thuộc

### 8.1. Nối không mất mát (*lossless-join decomposition*)

Giả sử phân rã \(R(U)\) thành các lược đồ \(R_1,\ldots,R_n\). Một phân rã **nối không mất mát theo \(F\)** nếu với **mọi quan hệ hợp lệ \(r\) thỏa \(F\)**:

\[
r = \Join_{i=1}^{n}\pi_{R_i}(r).
\]

Nói cách khác, khi chiếu bảng gốc ra các bảng con rồi **natural join** chúng lại, ta khôi phục chính xác các dòng của bảng gốc; không xuất hiện các dòng giả do ghép nhầm.

Với phân rã **hai bảng** \(R\to R_1,R_2\), điều kiện cần và đủ theo các phụ thuộc hàm là ít nhất một trong hai phụ thuộc sau suy ra được từ \(F\):

\[
(R_1\cap R_2)\rightarrow R_1
\qquad\text{hoặc}\qquad
(R_1\cap R_2)\rightarrow R_2.
\]

Ví dụ với \(R(A,B,C)\), \(F=\{A\rightarrow B\}\), phân rã thành \(R_1(A,B)\) và \(R_2(A,C)\) là **lossless** vì giao của hai tập cột là \(\{A\}\), và `A → AB` suy ra từ `A → B`.

Phản ví dụ dễ thấy: với \(R(A,B,C)\), không có phụ thuộc không tầm thường và dữ liệu:

| A | B | C |
|---|---|---|
| a1 | b1 | c1 |
| a2 | b1 | c2 |

Nếu tách thành \(R_1(A,B)\) và \(R_2(B,C)\), rồi nối trên `B`, ta còn có thêm `(a1,b1,c2)` và `(a2,b1,c1)` **không có trong dữ liệu gốc**. Đây là **nối mất mát** (*lossy decomposition*); dữ liệu đầu vào không nhất thiết bị xóa, nhưng phép tách đã làm mất thông tin về cặp ghép đúng.

### 8.2. Bảo toàn phụ thuộc (*dependency preservation*)

Với các quan hệ con \(R_i\), ký hiệu \(\pi_{R_i}(F)\) là **tập các phụ thuộc thuộc \(F^+\) mà tất cả thuộc tính đều nằm trong \(R_i\)**.

Phân rã **bảo toàn phụ thuộc** khi:

\[
\left(\bigcup_i\pi_{R_i}(F)\right)^+=F^+.
\]

Ý nghĩa thực hành: toàn bộ phụ thuộc ban đầu có thể được suy diễn từ những quy tắc áp dụng **riêng trên từng quan hệ con**, không cần ghép tất cả bảng để phát hiện vi phạm.

Hai tiêu chí **khác nhau**:

| Tiêu chí | Câu hỏi trả lời | Nếu không đạt |
|---|---|---|
| **Nối không mất mát** | Chiếu rồi nối có khôi phục đúng dữ liệu không? | Có thể sinh dòng giả khi join |
| **Bảo toàn phụ thuộc** | Các quy tắc hàm ban đầu có kiểm tra được qua các quan hệ con không? | Có phụ thuộc phải kiểm tra liên bảng hoặc khi join |

Đừng đánh đồng **bảo toàn phụ thuộc về mặt lý thuyết** với việc chỉ dùng `PRIMARY KEY` và `FOREIGN KEY` trong một DBMS là cưỡng chế được mọi phụ thuộc. Một số phụ thuộc cần cách bố trí bảng, ràng buộc bổ sung hoặc logic kiểm soát phù hợp.

## 9. Tổng hợp lược đồ 3NF từ phủ tối thiểu

**Thuật toán tổng hợp 3NF** (*3NF synthesis*) thường thực hiện:

1. Tìm một **phủ tối thiểu** \(G\) của \(F\), với vế phải một thuộc tính.
2. Với mỗi vế trái \(X\), tạo quan hệ \(R_X\) chứa \(X\) và tất cả các thuộc tính \(A\) sao cho \(X\rightarrow A\) thuộc \(G\). Gộp các phụ thuộc **cùng vế trái** để tránh tạo nhiều bảng không cần thiết.
3. Có thể bỏ quan hệ con có tập thuộc tính nằm hoàn toàn trong quan hệ con khác, theo phiên bản thuật toán chuẩn.
4. Nếu **chưa có quan hệ con nào chứa một khóa ứng viên của lược đồ gốc**, bổ sung một quan hệ chỉ gồm các thuộc tính của một khóa ứng viên.

Với cách thực hiện chuẩn, thuật toán cho một phân rã **đạt 3NF, bảo toàn phụ thuộc và nối không mất mát**. Bước bổ sung khóa là quan trọng đối với bảo đảm nối không mất mát.

### Áp dụng cho ví dụ \(R(A,B,C,D,E)\)

Phủ tối thiểu đã tìm được:

~~~text
G = {
    A → B,
    B → C,
    A → D,
    D → E
}
~~~

Nhóm theo vế trái:

| Nhóm phụ thuộc | Quan hệ tạo ra | Khóa của quan hệ con theo phụ thuộc được giữ |
|---|---|---|
| `A → B`, `A → D` | \(R_1(A,B,D)\) | `A` |
| `B → C` | \(R_2(B,C)\) | `B` |
| `D → E` | \(R_3(D,E)\) | `D` |

Trong quan hệ gốc, ta có:

~~~text
{A}+ = {A, B, C, D, E}
~~~

Vì `A` **không xuất hiện ở bất kỳ vế phải nào** và bao đóng của `A` là toàn bộ \(U\), `A` là khóa ứng viên của \(R\). Quan hệ \(R_1(A,B,D)\) đã chứa `A`, nên không cần thêm quan hệ khóa riêng.

**Bảo toàn phụ thuộc:** từng phụ thuộc trong \(G\) đều nằm trọn trong một trong ba quan hệ:

~~~text
R1(A,B,D): A → B, A → D
R2(B,C):   B → C
R3(D,E):   D → E
~~~

Vì \(G^+=F^+\), các phụ thuộc gốc được bảo toàn về mặt suy diễn.

**Nối không mất mát:** nối \(R_1(A,B,D)\) với \(R_2(B,C)\) trên `B` là lossless, vì `B → C` và giao bằng `B`. Sau đó nối với \(R_3(D,E)\) trên `D` cũng lossless, vì `D → E`. Do đó từ ba phép chiếu ta có thể khôi phục quan hệ gốc theo các quy tắc đã cho.

**3NF:** mỗi quan hệ con được tạo quanh một vế trái quyết định các thuộc tính còn lại và trong ví dụ này vế trái đó là khóa của chính quan hệ con; vì vậy ba quan hệ đều thỏa cả **BCNF**. Đây là đặc điểm của **ví dụ này**, không phải bảo đảm chung rằng tổng hợp 3NF luôn tạo BCNF.

### Khi phải bổ sung một bảng chứa khóa

Xét \(R(A,B,C)\) với \(F=\{A\rightarrow B\}\). Phủ tối thiểu là chính \(F\). Nếu chỉ tạo \(R_1(A,B)\), sẽ **bỏ sót thuộc tính \(C\)**.

Khóa ứng viên của quan hệ gốc là \(\{A,C\}\), vì:

~~~text
{A,C}+ = {A,B,C}
{A}+   = {A,B}
{C}+   = {C}
~~~

Cần thêm \(R_2(A,C)\). Phân rã \(R_1(A,B),R_2(A,C)\) nối không mất mát vì `A → AB`; `A → B` cũng được bảo toàn trong \(R_1\).

Đây là lý do **không được bỏ bước kiểm tra quan hệ chứa khóa ứng viên**, kể cả khi tất cả phụ thuộc trong phủ tối thiểu đã có nơi thể hiện.

## 10. Vì sao BCNF có thể đánh đổi khả năng bảo toàn phụ thuộc?

**BCNF** yêu cầu vế trái của **mọi phụ thuộc hàm không tầm thường** \(X\rightarrow Y\) phải là siêu khóa. Điều kiện này mạnh hơn 3NF, nhưng một số phép phân rã BCNF **không bảo toàn toàn bộ phụ thuộc**.

Xét quan hệ:

~~~text
ASSIGNMENT(student_id, course_id, instructor_id)
~~~

Giả sử:

- Mỗi cặp `(student_id, course_id)` được phân công **một** giảng viên.
- Mỗi giảng viên chỉ phụ trách **một môn**, nhưng có thể dạy nhiều sinh viên.

Ta có:

~~~text
F = {
    (student_id, course_id) → instructor_id,
    instructor_id           → course_id
}
~~~

Cả `(student_id, course_id)` và `(student_id, instructor_id)` đều là khóa ứng viên. Vì `course_id` thuộc khóa ứng viên đầu tiên, phụ thuộc `instructor_id → course_id` có vế phải là thuộc tính khóa, nên bảng **thỏa 3NF**. Tuy vậy `instructor_id` không là siêu khóa, nên bảng **vi phạm BCNF**.

Một phân rã BCNF:

~~~text
INSTRUCTOR_COURSE(instructor_id, course_id)
STUDENT_INSTRUCTOR(student_id, instructor_id)
~~~

Phân rã này **nối không mất mát**, vì giao hai bảng là `instructor_id` và `instructor_id → course_id` xác định toàn bộ `INSTRUCTOR_COURSE`.

Nhưng phụ thuộc:

~~~text
(student_id, course_id) → instructor_id
~~~

**không được bảo toàn qua các phụ thuộc chỉ trên từng bảng con**. Hai bảng có thể riêng lẻ hợp lệ nhưng một sinh viên có hai giảng viên khác nhau dạy cùng môn sau khi nối. Muốn cưỡng chế quy tắc “mỗi sinh viên-môn có một giảng viên”, hệ thống có thể phải kiểm tra liên bảng hoặc dùng giải pháp thiết kế khác.

| Mục tiêu | 3NF synthesis | Phân rã BCNF |
|---|---|---|
| Giảm dư thừa do phụ thuộc hàm | Có, đạt 3NF | Mạnh hơn, đạt BCNF |
| Nối không mất mát | Có với thuật toán chuẩn | Có thể đạt bằng thuật toán phân rã chuẩn |
| Bảo toàn mọi phụ thuộc hàm | Được bảo đảm với thuật toán tổng hợp chuẩn | **Không luôn được bảo đảm** |

Quyết định ưu tiên 3NF hay BCNF tùy thuộc **quy tắc cần cưỡng chế**, mức độ dư thừa chấp nhận được và chi phí vận hành. Không nên chỉ chọn dạng chuẩn cao hơn theo tên gọi.

## 11. Chuyển kết quả sang mô hình nghiệp vụ và lược đồ vật lý

Giả sử hệ thống bán hàng bắt đầu từ bảng gộp:

~~~text
ORDER_LINE_FLAT(
    order_id, line_no, order_date,
    customer_id, customer_name,
    product_id, product_name,
    quantity, unit_price_at_sale
)
~~~

Với quy tắc:

~~~text
order_id             → order_date, customer_id
customer_id          → customer_name
product_id           → product_name
(order_id, line_no)  → product_id, quantity, unit_price_at_sale
~~~

Tách vế phải cho ta một cách biểu diễn phủ tối thiểu; nếu không có quy tắc bổ sung, các vế trái trong bộ quy tắc trên không chứa thuộc tính thừa, và không phụ thuộc nào trong phiên bản tách vế phải được suy ra hoàn toàn từ các phụ thuộc còn lại.

Tổng hợp theo các nhóm phụ thuộc tạo ra bốn lược đồ:

~~~text
ORDERS(order_id, order_date, customer_id)
CUSTOMERS(customer_id, customer_name)
PRODUCTS(product_id, product_name)
ORDER_ITEMS(order_id, line_no, product_id, quantity, unit_price_at_sale)
~~~

Khóa ứng viên của quan hệ gốc là `(order_id, line_no)`; quan hệ `ORDER_ITEMS` chứa toàn bộ khóa này. Mỗi quy tắc trong phủ tối thiểu thuộc một bảng tương ứng. Các bảng mới lưu thông tin ở đúng **mức hạt**: đơn, khách hàng, sản phẩm hoặc dòng hàng.

Ví dụ DDL phù hợp với giả định tên khách và tên sản phẩm là **giá trị hiện hành**:

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
    order_date DATE NOT NULL,
    customer_id VARCHAR(30) NOT NULL REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_id VARCHAR(30) NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id VARCHAR(30) NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_sale DECIMAL(12,2) NOT NULL
        CHECK (unit_price_at_sale >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

**Không** đặt `UNIQUE(order_id, product_id)` nếu nghiệp vụ cho phép cùng sản phẩm xuất hiện hai dòng trong một đơn. **Không** đưa `unit_price_at_sale` vào `products` nếu cùng sản phẩm được bán ở các giá khác nhau. Phụ thuộc hàm hỗ trợ **nhận diện mức hạt và khóa**; các ràng buộc **khóa ngoại, miền giá trị, tính bắt buộc, lịch sử thay đổi** vẫn cần được thiết kế riêng.

Trong mô hình **document**, có thể nhúng các dòng vào document đơn hàng để đọc trọn đơn, nhưng phải xác định rõ trường nhúng nào là **ảnh chụp lịch sử** và trường nào cần cập nhật theo nguồn hiện hành. Với mô hình **đồ thị**, cần ràng buộc định danh thực thể và quan hệ trên node/edge. Với mô hình **phân tích**, mức hạt fact và phiên bản dimension quyết định phụ thuộc nào còn đúng. Phủ tối thiểu là công cụ hình thức cho **lược đồ quan hệ**, còn tư duy loại bỏ ràng buộc dư thừa và kiểm tra tính nhất quán có thể giúp so sánh các cách mô hình hóa.

## 12. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Xóa `X → A` sau khi tính `X+` với chính phụ thuộc đó vẫn nằm trong tập | Kết luận sai rằng mọi phụ thuộc đều dư | Tính bao đóng bằng **tập đã bỏ phụ thuộc đang kiểm tra** |
| Chỉ tách vế phải rồi gọi là phủ tối thiểu | Vẫn còn vế trái thừa và phụ thuộc dư | Rút gọn vế trái, xóa phụ thuộc dư, kiểm tra tương đương |
| Chỉ chứng minh tập mới suy ra tập cũ | Có thể đã thêm ràng buộc mạnh hơn nghiệp vụ | Chứng minh **hai chiều** \(F\models G\) và \(G\models F\) |
| Đòi phủ tối thiểu phải duy nhất | Bỏ qua nhiều kết quả hợp lệ | Kiểm tra thuộc tính, dư thừa và tính tương đương, không so giống hệt |
| Tạo bảng từ mọi phụ thuộc mà quên thêm bảng chứa khóa | Có thể thiếu thuộc tính hoặc không bảo đảm lossless | Thực hiện đủ thuật toán tổng hợp 3NF |
| Nghĩ lossless là dependency preserving | Có thể nối đúng nhưng mất khả năng kiểm tra phụ thuộc cục bộ | Kiểm tra từng tiêu chí độc lập |
| Luôn chuyển sang BCNF không xét nghiệp vụ | Có thể phải kiểm tra phụ thuộc qua nhiều bảng | Cân nhắc bảo toàn phụ thuộc với chi phí vận hành |
| Suy phụ thuộc từ dữ liệu hiện có mà không hỏi nghiệp vụ | Mô hình sai khi xuất hiện dữ liệu mới | Xác nhận phạm vi mã, ngoại lệ và thay đổi theo thời gian |

## 13. Bài luyện tập có lời giải

### Bài 1 — Tính phủ tối thiểu

Cho \(R(A,B,C,D)\):

~~~text
F = { A → BC, B → C, AC → D, A → D }
~~~

**Yêu cầu:** Tìm một phủ tối thiểu.

**Lời giải:** Tách `A → BC` thành `A → B` và `A → C`. Vì `A → B` và `B → C`, `A → C` dư. `AC → D` dư vì đã có `A → D` (hoặc nhận ra `C` thừa ở vế trái). Kết quả:

~~~text
G = { A → B, B → C, A → D }
~~~

\(G\) tương đương với \(F\) và không còn phụ thuộc dư theo các quy tắc đã cho.

### Bài 2 — Tại sao phép kiểm tra dư thừa phải bỏ phụ thuộc?

Cho \(F=\{A\rightarrow B,\ B\rightarrow C\}\). Có xóa được `A → B` không?

**Lời giải:** Không. Tính `{A}+` theo **`F - {A → B}`** chỉ thu được `{A}`. Thuộc tính `B` không nằm trong bao đóng này, nên `A → B` không dư. Nếu giữ chính `A → B` trong phép kiểm tra thì kết quả không có ý nghĩa.

### Bài 3 — Bổ sung bảng chứa khóa trong tổng hợp 3NF

Cho \(R(A,B,C,D)\), \(F=\{A\rightarrow B,\ C\rightarrow D\}\).

**Yêu cầu:** Xác định khóa ứng viên và các bảng sau tổng hợp 3NF.

**Lời giải:** `A` và `C` không xuất hiện ở vế phải, nên mọi khóa phải chứa cả hai. `{A,C}+=\{A,B,C,D\}`, vì vậy khóa ứng viên là `{A,C}`. Tạo `R1(A,B)` và `R2(C,D)` từ phủ tối thiểu, nhưng chưa bảng nào chứa khóa `AC`; thêm `R3(A,C)`. Khi đó phân rã bảo toàn các phụ thuộc ban đầu và nối không mất mát.

### Bài 4 — Nhận ra lossless và dependency preservation

Cho \(R(A,B,C)\), \(F=\{A\rightarrow B\}\). Phân rã thành `R1(A,B)` và `R2(A,C)`. Có lossless không? Có bảo toàn phụ thuộc không?

**Lời giải:** Có **lossless** vì phần giao `{A}` xác định `R1(A,B)`. Có **bảo toàn phụ thuộc** vì `A → B` có thể kiểm tra ngay trong `R1`.

### Bài 5 — Phân rã BCNF mất phụ thuộc nào?

Với `ASSIGNMENT(student_id, course_id, instructor_id)` và:

~~~text
(student_id, course_id) → instructor_id
instructor_id           → course_id
~~~

Phân rã thành `INSTRUCTOR_COURSE(instructor_id,course_id)` và `STUDENT_INSTRUCTOR(student_id,instructor_id)`.

**Lời giải:** Phân rã **lossless** nhờ `instructor_id → course_id`. Phụ thuộc `(student_id, course_id) → instructor_id` **không bảo toàn trên từng bảng con**: cả hai bảng không cùng chứa `student_id,course_id,instructor_id`, và tập phụ thuộc chiếu lên chúng không suy ra quy tắc này. Cần cân nhắc việc giữ 3NF hoặc triển khai kiểm tra nghiệp vụ liên bảng.

## 14. Checklist trước khi chốt phân rã

- [ ] Xác nhận các phụ thuộc ban đầu bằng **quy tắc nghiệp vụ**, không chỉ từ dữ liệu mẫu.
- [ ] Tách vế phải, kiểm tra thuộc tính thừa ở vế trái và phụ thuộc hàm dư.
- [ ] Kiểm tra tập rút gọn **tương đương hai chiều** với tập gốc.
- [ ] Xác định các khóa ứng viên bằng phép tính bao đóng.
- [ ] Khi tổng hợp 3NF, nhóm phụ thuộc cùng vế trái và kiểm tra đã có quan hệ chứa **khóa ứng viên của quan hệ gốc**.
- [ ] Kiểm tra phân rã **nối không mất mát** và **bảo toàn phụ thuộc**.
- [ ] Nếu chọn BCNF, đánh giá các phụ thuộc có thể không còn kiểm tra được trong từng bảng riêng.
- [ ] Ánh xạ khóa và liên kết sang `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`; bổ sung `NOT NULL`, `CHECK` theo yêu cầu.
- [ ] Làm rõ dữ liệu hiện hành, dữ liệu lịch sử, phạm vi định danh và mức hạt của mỗi bảng.

**Ghi nhớ:** Phủ tối thiểu là một **cách viết gọn tương đương về logic** của tập phụ thuộc hàm, không phải một tập quy tắc nghiệp vụ mới. Dùng nó để tổng hợp và kiểm tra lược đồ có hệ thống; một phép phân rã tốt phải giữ được **dữ liệu khi nối** và, khi cần, giữ được **khả năng kiểm tra các phụ thuộc**.

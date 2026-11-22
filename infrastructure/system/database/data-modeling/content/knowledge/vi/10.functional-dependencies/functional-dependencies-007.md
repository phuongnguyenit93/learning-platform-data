# Phụ thuộc nối và giới hạn khi phân rã thành nhiều quan hệ

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, mục tiêu là biến yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, có thể kiểm chứng và dễ tiến hóa: xác định thực thể, quan hệ, khóa, phụ thuộc, dạng chuẩn và cấu trúc vật lý phù hợp. Sau khi học phụ thuộc hàm (FD) và phụ thuộc đa trị (MVD), ta gặp một trường hợp khó hơn: **một quan hệ có thể chỉ được tái tạo đúng bằng phép nối từ ba hoặc nhiều phép chiếu khi có quy tắc nghiệp vụ rất cụ thể**.

Đó là chủ đề của **phụ thuộc nối** (*join dependency*, JD). Bài này giúp bạn:

- Giải thích JD bằng phép **chiếu** (*projection*) và **nối tự nhiên** (*natural join*), phân biệt một phân rã nối không mất mát với một phép nối sinh ra bộ giả.
- Chỉ ra vì sao các cặp quan hệ cùng hợp lệ **không nhất thiết** xác định đúng một quan hệ ba ngôi.
- Phân biệt JD, FD và MVD; hiểu vì sao một quan hệ đạt **4NF** vẫn có thể chưa đạt **5NF**.
- Kiểm chứng một phân rã nhiều quan hệ bằng quy tắc nghiệp vụ, dữ liệu đối chứng và truy vấn SQL.
- Cân nhắc việc phân rã với bảo toàn phụ thuộc, khả năng thực thi ràng buộc, chi phí nối và mô hình document, đồ thị, phân tích.

## 1. Vấn đề nghiệp vụ: ba thực thể và ba quan hệ từng cặp

Xét hệ thống phân phối với ba loại thực thể:

- **Nhà cung cấp** (`supplier_id`).
- **Linh kiện** (`part_id`).
- **Dự án** (`project_id`).

Hệ thống muốn quản lý các bộ ba `(supplier_id, part_id, project_id)\). Một bộ ba có thể mang **hai ý nghĩa nghiệp vụ hoàn toàn khác nhau**:

1. **Quyền được cung cấp:** nhà cung cấp được phép cung cấp linh kiện cho dự án nếu thỏa **đồng thời ba điều kiện độc lập theo từng cặp**: nhà cung cấp được duyệt cho linh kiện, nhà cung cấp được duyệt cho dự án, và linh kiện được chấp nhận trong dự án.
2. **Hợp đồng thực tế:** nhà cung cấp **đã được giao** cung cấp linh kiện cụ thể cho dự án cụ thể. Dù cả ba cặp đều được duyệt, không phải mọi bộ ba đều đã trở thành hợp đồng.

Với nghĩa thứ nhất, bộ ba có thể được **suy ra từ ba quan hệ cặp**. Với nghĩa thứ hai, bộ ba là **một sự kiện độc lập** phải được lưu riêng.

Sự phân biệt này quyết định liệu việc tách bảng thành nhiều quan hệ có khôi phục được dữ liệu mà **không tạo ra các bộ ba không có thật** hay không.

## 2. Ôn lại phép chiếu, phép nối và nối không mất mát

Gọi \(R(U)\) là một lược đồ quan hệ có tập thuộc tính \(U\); \(r\) là một trạng thái dữ liệu hợp lệ của \(R\).

- **Phép chiếu** \(\pi_V(r)\) giữ các thuộc tính trong \(V\subseteq U\) và, theo ngữ nghĩa tập hợp của mô hình quan hệ, loại các bộ trùng nhau.
- **Nối tự nhiên** \(r_1\bowtie r_2\) kết hợp các bộ có cùng giá trị trên các thuộc tính chung.

Nếu tách \(U\) thành các tập con \(R_1,R_2,\ldots,R_n\) sao cho:

\[
U=R_1\cup R_2\cup\cdots\cup R_n,
\]

thì phép phân rã **nối không mất mát** (*lossless-join decomposition*) theo các ràng buộc được xác nhận khi, với **mọi** trạng thái hợp lệ \(r\):

\[
r=\pi_{R_1}(r)\bowtie\pi_{R_2}(r)\bowtie\cdots\bowtie\pi_{R_n}(r).
\]

Nếu không thỏa, phép nối các phép chiếu có thể sinh ra **bộ giả** (*spurious tuple*): tổ hợp được tạo ra sau khi nối nhưng chưa từng có trong dữ liệu gốc.

Trong mô hình quan hệ dùng ngữ nghĩa tập hợp, nếu các phép chiếu bao phủ tất cả thuộc tính của \(R\), phép nối các phép chiếu luôn chứa các bộ gốc. Rủi ro chính là **sinh thêm bộ**. Tên gọi “phân rã mất mát” nói tới **mất thông tin về những kết hợp nào thực sự có mặt**, không nhất thiết là làm mất các giá trị thuộc tính.

## 3. Định nghĩa phụ thuộc nối (join dependency)

Một phụ thuộc nối trên \(R(U)\), ký hiệu:

\[
*\{R_1,R_2,\ldots,R_n\},
\]

trong đó mỗi \(R_i\subseteq U\) và \(\bigcup_iR_i=U\), phát biểu rằng **mọi trạng thái hợp lệ** \(r\) của \(R\) đều phải thỏa:

\[
\boxed{\quad
r=\bowtie_{i=1}^{n}\pi_{R_i}(r)
\quad}
\]

Nói cách khác, quan hệ gốc **được xác định đầy đủ** bởi các phép chiếu của nó lên những tập thuộc tính này.

Ví dụ, với:

~~~text
SUPPLY(supplier_id, part_id, project_id)
~~~

ta có thể xét JD:

~~~text
*{
    (supplier_id, part_id),
    (supplier_id, project_id),
    (part_id, project_id)
}
~~~

JD này chỉ đúng khi **mọi bộ ba được ba quan hệ cặp cho phép đều phải có trong quan hệ gốc**, và mọi bộ ba trong quan hệ gốc tất nhiên phải có ba cặp tương ứng. Đây là một **quy tắc mạnh**, cần sự xác nhận từ nghiệp vụ.

### JD tầm thường và không tầm thường

JD là **tầm thường** nếu có ít nhất một tập thuộc tính \(R_i=U\). Khi đó một phép chiếu chính là toàn bộ quan hệ gốc, nên điều kiện nối không thêm thông tin độc lập mới.

JD là **không tầm thường** khi không tập \(R_i\) nào bằng \(U\). Phụ thuộc ba phép chiếu `(supplier_id,part_id)`, `(supplier_id,project_id)`, `(part_id,project_id)` ở trên là JD không tầm thường vì mỗi phép chiếu đều bỏ đi một thuộc tính.

**Lưu ý:** dữ liệu mẫu vô tình thỏa phép nối không đủ chứng minh JD là ràng buộc đúng trên **mọi dữ liệu hợp lệ trong tương lai**. Cách xác định vẫn là từ yêu cầu nghiệp vụ.

## 4. Phản ví dụ: ba quan hệ cặp tạo ra bộ ba giả

Giả sử bảng `SUPPLY` đang lưu **ba hợp đồng thực tế**:

| supplier_id | part_id | project_id |
|---|---|---|
| S1 | P1 | J2 |
| S1 | P2 | J1 |
| S2 | P1 | J1 |

Chiếu ra ba tập thuộc tính cặp:

**SUPPLIER_PART**

| supplier_id | part_id |
|---|---|
| S1 | P1 |
| S1 | P2 |
| S2 | P1 |

**SUPPLIER_PROJECT**

| supplier_id | project_id |
|---|---|
| S1 | J2 |
| S1 | J1 |
| S2 | J1 |

**PART_PROJECT**

| part_id | project_id |
|---|---|
| P1 | J2 |
| P2 | J1 |
| P1 | J1 |

Bây giờ nối cả ba bảng cặp:

~~~sql
SELECT sp.supplier_id, sp.part_id, sj.project_id
FROM supplier_part AS sp
JOIN supplier_project AS sj
  ON sj.supplier_id = sp.supplier_id
JOIN part_project AS pj
  ON pj.part_id = sp.part_id
 AND pj.project_id = sj.project_id;
~~~

Ngoài ba dòng gốc, truy vấn còn tạo thêm:

~~~text
(S1, P1, J1)    -- bộ ba giả so với hợp đồng gốc
~~~

Vì:

- `(S1,P1)` có trong `SUPPLIER_PART`.
- `(S1,J1)` có trong `SUPPLIER_PROJECT`.
- `(P1,J1)` có trong `PART_PROJECT`.

Nhưng không có hợp đồng thực tế `(S1,P1,J1)` trong bảng ban đầu.

<details>
<summary>Vì sao nối ba quan hệ vẫn có thể sinh bộ giả?</summary>

Điều kiện “**ba cặp đều tồn tại**” yếu hơn điều kiện “**bộ ba thực tế tồn tại**”. Một cặp nhà cung cấp–linh kiện có thể đến từ hợp đồng cho dự án này, cặp nhà cung cấp–dự án đến từ hợp đồng với linh kiện khác, và cặp linh kiện–dự án đến từ nhà cung cấp khác. Phép nối ghép các chứng cứ từng cặp thành một bộ ba chưa có trong hệ thống.

</details>

Vậy với ngữ nghĩa **hợp đồng thực tế**, JD `*{SP,SJ,PJ}` **không đúng**; phân rã thành ba bảng cặp là **mất thông tin về bộ ba**. Đây là lý do không thể tùy tiện xóa một quan hệ ba ngôi chỉ vì có ba quan hệ hai ngôi.

## 5. Khi nào JD ba ngôi thật sự đúng?

Giữ ba thực thể trên nhưng đổi **quy tắc nghiệp vụ** thành:

> Một nhà cung cấp **được phép** cung cấp linh kiện cho một dự án **khi và chỉ khi** cả ba cặp tương ứng đều được phê duyệt. Không có ràng buộc bổ sung ở cấp bộ ba.

Khi đó tập các bộ ba hợp lệ có thể **được định nghĩa** bởi phép nối:

~~~text
ELIGIBLE_SUPPLY =
    SUPPLIER_PART
    ⋈ SUPPLIER_PROJECT
    ⋈ PART_PROJECT
~~~

Giả sử ba quan hệ cặp như ở phần trước. Ta **bắt buộc chấp nhận** thêm `(S1,P1,J1)` như một **quyền được phép**; nếu chưa có hợp đồng, đó vẫn có thể là quyền hợp lệ.

Trong tập các bộ ba quyền được phép lúc này có bốn dòng:

| supplier_id | part_id | project_id |
|---|---|---|
| S1 | P1 | J2 |
| S1 | P2 | J1 |
| S2 | P1 | J1 |
| S1 | P1 | J1 |

Chiếu rồi nối lại không sinh dòng thứ năm. JD được thỏa trong ví dụ này, và quy tắc **“khi và chỉ khi”** là căn cứ để yêu cầu JD đúng với dữ liệu hợp lệ nói chung.

### Hai bảng có thể cần cùng tồn tại

Trong ứng dụng thật, rất có thể cần **cả hai khái niệm**:

~~~text
ELIGIBLE_SUPPLY   -- quyền cung cấp, được suy ra từ các phê duyệt cặp
ACTUAL_CONTRACTS  -- hợp đồng đã ký, lưu sự kiện bộ ba độc lập
~~~

`ACTUAL_CONTRACTS` có thể dùng khóa `contract_id` và tham chiếu tới một bộ ba đang được phép, nhưng còn có các thuộc tính hợp đồng như ngày ký, số lượng, giá, hiệu lực. Không được coi một quyền được phép là một hợp đồng đã phát sinh.

Một thay đổi nhỏ trong định nghĩa nghiệp vụ làm thay đổi hoàn toàn câu trả lời về JD. Đó là lý do phải xác định **ý nghĩa một dòng dữ liệu** trước khi chuẩn hóa.

## 6. Sơ đồ minh họa các bộ ba được suy ra

~~~mermaid
flowchart LR
    SP["Nhà cung cấp – Linh kiện\n(S, P)"] --> J["Nối theo khóa chung"]
    SJ["Nhà cung cấp – Dự án\n(S, J)"] --> J
    PJ["Linh kiện – Dự án\n(P, J)"] --> J
    J --> E["Bộ ba đủ điều kiện\n(S, P, J)"]
~~~

Sơ đồ chỉ đúng cho quy tắc **quyền được phép xác định bởi ba phê duyệt cặp**. Trong mô hình **hợp đồng thực tế**, phải có thêm thực thể/sự kiện ghi nhận bộ ba; không dùng kết quả nối làm bằng chứng hợp đồng.

## 7. JD liên hệ thế nào với phụ thuộc hàm và phụ thuộc đa trị?

### 7.1. Phụ thuộc hàm (FD)

FD:

\[
X\rightarrow Y
\]

nghĩa là mỗi giá trị \(X\) xác định **một giá trị** \(Y\) trong mọi trạng thái hợp lệ.

Ví dụ `order_id → customer_id` có thể giúp nhận diện mức hạt một đơn hàng. FD cũng cung cấp điều kiện kiểm tra lossless cho phân rã **hai quan hệ** dưới một tập FD:

Với \(R\rightarrow R_1,R_2\), phân rã nối không mất mát theo \(F\) nếu và chỉ nếu:

\[
(R_1\cap R_2)\rightarrow R_1
\quad\text{hoặc}\quad
(R_1\cap R_2)\rightarrow R_2
\]

được suy ra từ \(F\).

Ví dụ \(R(A,B,C)\), \(F=\{A\rightarrow B\}\), tách thành `R1(A,B)` và `R2(A,C)` là lossless, vì phần giao \(\{A\}\) xác định \(\{A,B\}\).

**Giới hạn:** tiêu chí đơn giản trên áp dụng trực tiếp cho một phân rã **hai quan hệ theo các FD**. Không được kiểm tra rời rạc tất cả cặp trong một phép phân rã ba, bốn bảng rồi kết luận tự động rằng toàn bộ phép nối là lossless.

### 7.2. Phụ thuộc đa trị (MVD)

MVD:

\[
X\twoheadrightarrow Y
\]

phát biểu rằng, khi giữ \(X\) cố định, các giá trị của \(Y\) **độc lập** với phần thuộc tính còn lại \(Z=U-(X\cup Y)\).

Trên \(R(X,Y,Z)\), MVD tương đương với JD hai phép chiếu:

\[
X\twoheadrightarrow Y
\quad\Longleftrightarrow\quad
*\{XY,XZ\}.
\]

Ví dụ, với `EMPLOYEE_PROFILE(employee_id,skill,language)`, khi tập kỹ năng và ngôn ngữ **độc lập**, ta có `employee_id ↠ skill` và có thể tách `(employee_id,skill)`, `(employee_id,language)` một cách lossless theo MVD.

### 7.3. JD tổng quát

JD tổng quát có thể cần **ba hoặc nhiều phép chiếu**. Với `SUPPLY(S,P,J)`, quy tắc:

~~~text
*{ (S,P), (S,J), (P,J) }
~~~

đòi hỏi **tất cả ba cặp cùng có mặt** thì bộ ba cũng có mặt. Đây không phải chỉ là cách viết tắt cho một FD hay một MVD hai phép chiếu bất kỳ.

| Loại ràng buộc | Câu hỏi chính | Phép phân rã liên quan |
|---|---|---|
| **FD** \(X\rightarrow Y\) | Một \(X\) xác định duy nhất \(Y\)? | Tìm khóa, 2NF/3NF/BCNF, nhiều phép tách hai bảng |
| **MVD** \(X\twoheadrightarrow Y\) | Tập \(Y\) độc lập với phần \(Z\) khi giữ \(X\)? | Hai phép chiếu `XY` và `XZ`, 4NF |
| **JD** \(*\{R_1,\ldots,R_n\}\) | Nối tất cả phép chiếu có khôi phục **đúng** quan hệ? | Phân rã tổng quát, đặc biệt nhiều phép chiếu, 5NF |

FD có thể dẫn tới một JD đặc biệt, MVD là một dạng JD hai phép chiếu, nhưng **không phải mọi JD đều suy được từ FD hoặc MVD**. Chính phần còn lại này là động cơ của 5NF.

## 8. Dạng chuẩn 5NF và giới hạn của 4NF

**Dạng chuẩn năm** (*Fifth Normal Form, 5NF*), còn gọi là **project-join normal form (PJNF)**, yêu cầu rằng **mọi JD không tầm thường** đúng trên quan hệ phải **được suy ra từ các khóa ứng viên** của quan hệ.

Diễn giải thực hành: không còn phép phân rã nối không mất mát, **không tầm thường và có ý nghĩa chuẩn hóa**, mà sự đúng đắn của nó phụ thuộc vào một quy tắc JD độc lập chưa được bảo đảm bởi các khóa.

Trong quan hệ `SUPPLY(S,P,J)` mô tả **quyền được phép** theo quy tắc ba cặp:

- Giả sử không có FD không tầm thường nào giữa `S`, `P`, `J`: một nhà cung cấp có nhiều linh kiện và dự án; một linh kiện có nhiều nhà cung cấp và dự án; một dự án có nhiều nhà cung cấp và linh kiện.
- Khóa ứng viên của quan hệ bộ ba là `(S,P,J)`, vì không có tập thuộc tính nhỏ hơn xác định toàn bộ bộ ba theo các FD được xác nhận.
- Nếu không có MVD không tầm thường nào khác, quan hệ có thể đã đạt **4NF**.
- Nhưng JD `*{SP,SJ,PJ}` vẫn đúng do nghiệp vụ quy định; nó **không được suy ra chỉ từ khóa (S,P,J)**.

Vì vậy quan hệ quyền được phép chưa ở **5NF** và có thể phân rã thành ba quan hệ cặp để tránh lưu lặp bộ ba.

Điểm cần nhớ: **4NF xử lý MVD không tầm thường; 5NF còn xét JD nhiều phép chiếu**. Không thể kết luận một bảng đã hết mọi dư thừa do phép nối chỉ vì đã đạt BCNF hoặc 4NF.

### Không suy ra 5NF chỉ bằng đếm cột

Một bảng có ba thuộc tính **không tự động** có JD không tầm thường, và bảng có nhiều hơn ba thuộc tính **không nhất thiết** phải tách. Chỉ nên đề xuất phân rã khi quy tắc nghiệp vụ thực sự bảo đảm phép **chiếu rồi nối lại không sinh bộ giả**.

## 9. Phân rã nhiều bảng: điều gì có thể và không thể bảo đảm?

Với nhiều quan hệ con, có ba nhóm câu hỏi khác nhau:

| Khía cạnh | Câu hỏi phải trả lời | Cách tiếp cận |
|---|---|---|
| **Nối không mất mát** | Nối các bảng có tạo bộ giả không? | Chứng minh JD bằng ràng buộc nghiệp vụ, phép suy diễn hoặc kỹ thuật *chase* |
| **Bảo toàn phụ thuộc** | Những FD/JD ban đầu có còn kiểm tra được trên các bảng con không? | Xem tập ràng buộc chiếu lên từng bảng và các ràng buộc liên bảng cần thiết |
| **Chi phí vận hành** | Đọc, ghi, chỉ mục và kiểm tra toàn vẹn có đáp ứng workload không? | Đo truy vấn, số bộ trung gian, tần suất cập nhật, chi phí join |

Một phép phân rã **lossless** vẫn có thể **không bảo toàn các phụ thuộc hàm** theo cách kiểm tra cục bộ.

### Ví dụ lossless nhưng không bảo toàn một FD

Cho \(R(A,B,C)\) với:

~~~text
F = {
    AB → C,
    C  → B
}
~~~

Phân rã thành `R1(C,B)` và `R2(A,C)` là **lossless**, vì giao của hai quan hệ là `C`, và `C → B`.

Tuy nhiên, `AB → C` **không được bảo toàn** chỉ bằng các FD trên từng bảng con. Có thể có:

~~~text
R1(C,B) = {(c1,b1), (c2,b1)}   -- thỏa C → B
R2(A,C) = {(a1,c1), (a1,c2)}
~~~

Từng bảng con hợp lệ theo các phụ thuộc cục bộ, nhưng khi nối:

~~~text
(a1,b1,c1)
(a1,b1,c2)
~~~

ta được cùng `(A,B)` với hai giá trị `C`, **vi phạm `AB → C`**. Do đó có thể phải kiểm soát quy tắc này qua nhiều bảng hoặc chọn cách phân rã khác.

**Phân rã đúng dữ liệu khi nối** và **bảo toàn khả năng cưỡng chế phụ thuộc** là hai yêu cầu khác nhau. Trong thiết kế thực tế, cần đưa cả hai vào tiêu chí quyết định.

### Vì sao quy tắc cho hai bảng không đủ khi có nhiều bảng?

Với `SUPPLY(S,P,J)`, ba cặp `SP`, `SJ`, `PJ` đều có giao thuộc tính với nhau. Chỉ việc có các cột chung không đảm bảo tổ hợp ba chiều là một bộ thực tế. Nếu xem toàn bộ phép nối là một chuỗi các bước, việc chứng minh mỗi bước đúng đòi hỏi xét **quan hệ trung gian** và **các phụ thuộc thực sự đúng** trên nó; kiểm tra từng cặp một cách riêng biệt là thiếu.

Với lược đồ phức tạp, có thể dùng phương pháp **tableau/chase** để kiểm tra lossless join theo tập ràng buộc cho trước. Phép kiểm tra phải bao gồm các FD, MVD/JD được xác nhận và hiểu rõ phạm vi bài toán; không tự lấy kết quả một phép join trên mẫu dữ liệu làm chứng minh tổng quát.

## 10. Kiểm chứng bằng SQL: tìm bộ ba được nối ra nhưng chưa từng có

Giả sử một bảng staging lưu bộ ba:

~~~text
staging_supply(supplier_id, part_id, project_id)
~~~

Để kiểm tra **trạng thái dữ liệu hiện tại** có thỏa JD `*{SP,SJ,PJ}` hay không, thực hiện:

~~~sql
WITH triples AS (
    SELECT DISTINCT supplier_id, part_id, project_id
    FROM staging_supply
    WHERE supplier_id IS NOT NULL
      AND part_id IS NOT NULL
      AND project_id IS NOT NULL
),
sp AS (
    SELECT DISTINCT supplier_id, part_id
    FROM triples
),
sj AS (
    SELECT DISTINCT supplier_id, project_id
    FROM triples
),
pj AS (
    SELECT DISTINCT part_id, project_id
    FROM triples
)
SELECT
    sp.supplier_id,
    sp.part_id,
    sj.project_id
FROM sp
JOIN sj
  ON sj.supplier_id = sp.supplier_id
JOIN pj
  ON pj.part_id = sp.part_id
 AND pj.project_id = sj.project_id
WHERE NOT EXISTS (
    SELECT 1
    FROM triples AS t
    WHERE t.supplier_id = sp.supplier_id
      AND t.part_id = sp.part_id
      AND t.project_id = sj.project_id
)
ORDER BY sp.supplier_id, sp.part_id, sj.project_id;
~~~

Mỗi dòng trả về là một **bộ ba mới được sinh từ ba phép chiếu nhưng thiếu trong bảng gốc**. Với bảng ba hợp đồng ở phần 4, truy vấn trả về:

~~~text
S1 | P1 | J1
~~~

Từ góc nhìn lý thuyết, đây là **phản ví dụ của JD trên trạng thái đang xét**. Từ góc nhìn nghiệp vụ, cần quyết định:

- Nếu `staging_supply` ghi **hợp đồng thực tế**, dòng thiếu là hợp lệ; việc phân rã thành ba bảng cặp mới là giả định sai.
- Nếu `staging_supply` bắt buộc chứa **mọi bộ ba đủ điều kiện theo ba cặp**, dòng thiếu có thể là vấn đề đồng bộ hoặc dữ liệu chưa đủ; phải điều tra trước khi sửa.

**Giới hạn của truy vấn:**

- Nó bỏ các dòng có `NULL` và dùng `DISTINCT` để gần ngữ nghĩa tập hợp. Cần kiểm tra riêng dữ liệu thiếu/trùng.
- Truy vấn không trả dòng nào **không chứng minh** JD sẽ đúng cho mọi dữ liệu tương lai.
- Với tập dữ liệu lớn, phép nối ba chiều có thể tạo số lượng tổ hợp trung gian lớn; cần chọn phạm vi thử nghiệm và kiểm tra kế hoạch truy vấn.
- SQL thường dùng ngữ nghĩa **đa tập** (*bag semantics*); JD của mô hình quan hệ dùng **tập hợp**. Cần phân biệt số dòng trùng do join với các bộ ba có giá trị khác nhau.

### Kiểm tra độ phình của phép nối

Một kiểm tra phụ trợ:

~~~sql
WITH sp AS (
    SELECT DISTINCT supplier_id, part_id FROM staging_supply
    WHERE supplier_id IS NOT NULL AND part_id IS NOT NULL
),
sj AS (
    SELECT DISTINCT supplier_id, project_id FROM staging_supply
    WHERE supplier_id IS NOT NULL AND project_id IS NOT NULL
),
pj AS (
    SELECT DISTINCT part_id, project_id FROM staging_supply
    WHERE part_id IS NOT NULL AND project_id IS NOT NULL
)
SELECT COUNT(*) AS joined_triples
FROM sp
JOIN sj ON sj.supplier_id = sp.supplier_id
JOIN pj
  ON pj.part_id = sp.part_id
 AND pj.project_id = sj.project_id;
~~~

Truy vấn này hữu ích để **ước lượng khối lượng kết quả**; nếu nguồn có `NULL`, bộ lọc của từng quan hệ chiếu có thể khác với truy vấn kiểm tra JD ở trên. Muốn so sánh số bộ **chính xác**, hãy dùng cùng một CTE `triples` không NULL cho cả ba phép chiếu và nguồn gốc.

## 11. Lược đồ SQL khi nghiệp vụ thực sự chỉ cần ba phê duyệt cặp

Nếu chỉ cần xác định **quyền được phép**, ta có thể lưu ba quan hệ cơ sở:

~~~sql
CREATE TABLE suppliers (
    supplier_id VARCHAR(30) PRIMARY KEY,
    supplier_name VARCHAR(200) NOT NULL
);

CREATE TABLE parts (
    part_id VARCHAR(30) PRIMARY KEY,
    part_name VARCHAR(200) NOT NULL
);

CREATE TABLE projects (
    project_id VARCHAR(30) PRIMARY KEY,
    project_name VARCHAR(200) NOT NULL
);

CREATE TABLE supplier_parts (
    supplier_id VARCHAR(30) NOT NULL REFERENCES suppliers(supplier_id),
    part_id VARCHAR(30) NOT NULL REFERENCES parts(part_id),
    PRIMARY KEY (supplier_id, part_id)
);

CREATE TABLE supplier_projects (
    supplier_id VARCHAR(30) NOT NULL REFERENCES suppliers(supplier_id),
    project_id VARCHAR(30) NOT NULL REFERENCES projects(project_id),
    PRIMARY KEY (supplier_id, project_id)
);

CREATE TABLE project_parts (
    project_id VARCHAR(30) NOT NULL REFERENCES projects(project_id),
    part_id VARCHAR(30) NOT NULL REFERENCES parts(part_id),
    PRIMARY KEY (project_id, part_id)
);
~~~

Danh sách bộ ba đủ điều kiện được tính bằng:

~~~sql
SELECT
    sp.supplier_id,
    sp.part_id,
    sj.project_id
FROM supplier_parts AS sp
JOIN supplier_projects AS sj
  ON sj.supplier_id = sp.supplier_id
JOIN project_parts AS pp
  ON pp.project_id = sj.project_id
 AND pp.part_id = sp.part_id;
~~~

Ưu điểm của cấu trúc này:

- Mỗi phê duyệt cặp được lưu **một lần**.
- Các khóa chính ghép ngăn trùng một cặp.
- Các khóa ngoại bảo đảm giá trị tham chiếu tồn tại.
- Quyền cung cấp bộ ba **được suy ra nhất quán** từ ba nguồn cặp theo quy tắc đã xác nhận.

Tuy nhiên, nếu cần ghi nhận **hợp đồng đã ký**, không sử dụng phép join trên làm bản ghi hợp đồng. Hãy thêm bảng thực thể/sự kiện phù hợp, ví dụ:

~~~sql
CREATE TABLE supply_contracts (
    contract_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supplier_id VARCHAR(30) NOT NULL REFERENCES suppliers(supplier_id),
    part_id VARCHAR(30) NOT NULL REFERENCES parts(part_id),
    project_id VARCHAR(30) NOT NULL REFERENCES projects(project_id),
    signed_on DATE NOT NULL
);
~~~

Nếu quy định mỗi hợp đồng phải thuộc **bộ ba được phê duyệt tại thời điểm ký**, cần thiết kế cơ chế kiểm tra ba cặp theo thời điểm, có thể bằng giao dịch, trigger, dịch vụ nghiệp vụ hoặc cấu trúc bổ sung. Các khóa ngoại đơn tới ba bảng thực thể **không tự kiểm tra** đủ ba phê duyệt cặp.

### Những điều phải cân nhắc trong lược đồ vật lý

Phân rã có thể làm giảm lưu trữ trùng nhưng tăng số phép nối khi đọc. Chỉ mục trên khóa ghép hỗ trợ một số đường truy cập; truy vấn đảo chiều, chẳng hạn tìm tất cả nhà cung cấp của một linh kiện, có thể cần chỉ mục bổ sung. Cần kiểm thử theo dữ liệu và workload thay vì suy rằng 5NF luôn nhanh hơn.

Với báo cáo đọc nhiều, có thể cân nhắc **view** hoặc **materialized view** cho bộ ba được phép; khi materialize, phải đảm bảo cơ chế cập nhật và tính nhất quán theo dữ liệu nguồn. Việc lưu lại bộ ba để tăng tốc không thay đổi **định nghĩa nghiệp vụ** của nó.

## 12. Giới hạn phân rã và lựa chọn mô hình dữ liệu

### Một quan hệ nhiều chiều có thể mang ý nghĩa không tách được

Ví dụ `DOCTOR_PATIENT_TREATMENT(doctor_id,patient_id,treatment_id)` có thể diễn đạt sự kiện **bác sĩ thực hiện phương pháp điều trị cho một bệnh nhân**. Ba quan hệ cặp:

~~~text
DOCTOR_PATIENT
DOCTOR_TREATMENT
PATIENT_TREATMENT
~~~

không đủ chứng minh một bộ ba điều trị đã diễn ra. Nếu ghi nhận sự kiện thực tế, hãy giữ quan hệ ba ngôi hoặc thực thể sự kiện với các thuộc tính thời gian, địa điểm, mã lần thực hiện.

### Phân rã quá nhiều có thể gây phức tạp

Ngay cả khi lossless về lý thuyết, số bảng lớn có thể:

- Tăng chi phí join, lượng dữ liệu trung gian và độ phức tạp truy vấn.
- Làm khó việc cưỡng chế các ràng buộc nghiệp vụ phải kiểm tra **liên bảng**.
- Gây khó khăn trong cập nhật giao dịch, khóa đồng thời và quản lý lịch sử.
- Làm thay đổi cách diễn giải dữ liệu nếu không thống nhất **mức hạt** và thời gian hiệu lực.

Vì thế, cần đánh giá **tính đúng đắn trước**, rồi đến yêu cầu truy vấn, chỉ mục và chi phí vận hành. Không nên tách mọi bảng ba cột thành các cặp chỉ để tăng mức chuẩn hóa trên giấy.

### Mô hình quan hệ, document, đồ thị và phân tích

| Mô hình | Cách diễn đạt quan hệ ba ngôi / JD | Rủi ro cần tránh |
|---|---|---|
| **Quan hệ** | Ba bảng cặp khi nghiệp vụ xác nhận JD; giữ bảng bộ ba nếu đó là sự kiện độc lập | Bộ giả khi join, bỏ sót phụ thuộc cần kiểm tra liên bảng |
| **Document** | Document về hợp đồng có thể chứa bộ ba; quyền cặp có thể lưu riêng hoặc nhúng theo nhu cầu truy vấn | Tưởng dữ liệu nhúng/tổng hợp là chứng cứ cho mọi tổ hợp hợp lệ |
| **Đồ thị** | Ba loại cạnh biểu diễn quan hệ cặp; bộ ba thực tế có thể cần nút sự kiện hoặc cấu trúc tái hóa quan hệ | Ba cạnh theo cặp không chứng minh một quan hệ ba ngôi thực tế |
| **Phân tích** | Fact table giữ đúng mức hạt sự kiện; bridge table ghi quan hệ nhiều-nhiều có quy tắc rõ | Nối nhiều bridge sinh tổ hợp giả, nhân đôi số liệu đo lường |

Ở mô hình đồ thị, một tam giác ba cạnh có thể đại diện **ba quan hệ từng cặp** mà không có ý nghĩa “đã có giao dịch ba bên”. Với mô hình phân tích, join các bảng bridge cần chú ý số dòng và mức hạt trước khi tính `SUM`, `COUNT`, hay chỉ số kinh doanh.

## 13. Quy trình đánh giá một phân rã nhiều quan hệ

### Bước 1 — Viết chính xác câu nghiệp vụ

Hỏi: “Bộ ba có thật khi **từng cặp đều hợp lệ**, hay còn cần một sự kiện/duyệt riêng ở cấp bộ ba?” Câu này quyết định có JD hay không.

### Bước 2 — Xác định mức hạt, phạm vi và thời gian

Mỗi dòng là **quyền**, **hợp đồng**, **lần thực hiện**, hay **bản ghi lịch sử**? Các cặp được duyệt ở **cùng thời điểm** không? Nếu dữ liệu phê duyệt có thời hạn, cần mô hình hóa thời gian hiệu lực phù hợp; nối các cặp từ những thời điểm khác nhau có thể sinh quyền giả.

### Bước 3 — Xây dựng và xác nhận phụ thuộc

Liệt kê FD, MVD, JD dựa trên quy tắc đã xác nhận. Với JD, nêu rõ tập thuộc tính của **từng phép chiếu** và yêu cầu **mọi tổ hợp được phép đều có mặt**. Không suy JD chỉ vì kết quả join trên vài dòng không có bộ giả.

### Bước 4 — Thử phản ví dụ

Tạo tình huống các cặp đều tồn tại nhưng **bộ ba chưa có**. Nếu nghiệp vụ vẫn coi đây là trạng thái hợp lệ, JD đề xuất **sai**. Nếu bộ ba bắt buộc hợp lệ, phải đảm bảo hệ thống có cơ chế sinh hoặc diễn giải nó.

### Bước 5 — Chứng minh lossless và kiểm tra bảo toàn phụ thuộc

Với hai bảng theo FD có thể dùng điều kiện giao xác định một bảng. Với nhiều phép chiếu hoặc JD phức tạp, cần chứng minh bằng các ràng buộc có thật hoặc dùng công cụ suy diễn thích hợp như *chase*. Kiểm tra riêng các FD/JD cần kiểm soát có còn triển khai được qua các bảng sau tách.

### Bước 6 — Thiết kế vật lý và kiểm thử truy vấn

Chọn khóa chính, khóa ngoại, chỉ mục và cơ chế kiểm soát thay đổi theo nghiệp vụ. Đo chi phí join với dữ liệu đại diện; kiểm tra các trường hợp được phép, bị cấm, không có dữ liệu, trùng và lịch sử. Nếu cần denormalize cho báo cáo, ghi rõ **nguồn chân lý** và cách đồng bộ.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả | Cách sửa |
|---|---|---|
| “Ba quan hệ cặp đủ đại diện cho mọi quan hệ ba ngôi” | Sinh bộ ba giả | Xác nhận quy tắc JD; nếu bộ ba là sự kiện, giữ quan hệ bộ ba |
| “Một phép nối không sinh bộ giả trên mẫu nên phân rã luôn lossless” | Sai khi dữ liệu mới xuất hiện | Chứng minh với mọi trạng thái hợp lệ và tìm phản ví dụ |
| “Đã BCNF/4NF thì chắc chắn không cần xét JD” | Bỏ sót dư thừa liên quan 5NF | Đánh giá JD không tầm thường không suy từ khóa |
| “JD là MVD có thêm nhiều thuộc tính ở vế phải” | Hiểu sai ràng buộc nhiều phép chiếu | MVD là trường hợp đặc biệt của JD **hai phép chiếu** |
| “Lossless đồng nghĩa bảo toàn phụ thuộc” | Ràng buộc phải kiểm tra qua nhiều bảng | Kiểm tra hai tính chất độc lập |
| “Khóa ngoại tới ba bảng thực thể đảm bảo ba cặp được duyệt” | Chấp nhận bộ ba chưa được phê duyệt | Kiểm tra các quan hệ cặp hoặc áp dụng ràng buộc nghiệp vụ tương ứng |
| “5NF luôn có hiệu năng tốt hơn” | Quá nhiều join hoặc phức tạp cập nhật | Đo workload và thiết kế chỉ mục, view phù hợp |
| “Mỗi cặp hợp lệ ở thời điểm khác nhau vẫn tạo bộ ba hợp lệ” | Sinh quyền/hợp đồng sai thời điểm | Xét thời gian hiệu lực của cả ba quan hệ |

## 15. Bài luyện tập có lời giải

### Bài 1 — Phát hiện bộ ba giả

Cho `R(S,P,J)`:

~~~text
(S1,P1,J2)
(S1,P2,J1)
(S2,P1,J1)
~~~

Phân rã `R` thành `SP`, `SJ`, `PJ` rồi nối lại. Bộ ba mới nào xuất hiện?

**Lời giải:** `(S1,P1,J1)`. Cặp `S1–P1`, `S1–J1`, `P1–J1` đều có trong ba phép chiếu, nên phép nối tạo bộ ba này dù nó không có trong \(R\) ban đầu. Phân rã **không lossless** trên trạng thái đó.

### Bài 2 — Khi nào bộ ba mới là hợp lệ?

Quy định: “Một nhà cung cấp được phép cung cấp linh kiện cho dự án **khi và chỉ khi** nhà cung cấp được duyệt cho linh kiện, nhà cung cấp được duyệt cho dự án, và linh kiện được phép dùng trong dự án.” Bộ ba `(S1,P1,J1)` có ba cặp được duyệt nhưng chưa có đơn đặt hàng.

**Lời giải:** Bộ ba này **đủ điều kiện được phép**, vì quy tắc định nghĩa nó bằng ba cặp; nó **chưa phải đơn đặt hàng hoặc hợp đồng thực tế**. Có thể dùng join ba bảng cặp để suy quyền; cần bảng giao dịch riêng để ghi sự kiện đã phát sinh.

### Bài 3 — Phân biệt FD, MVD và JD

Trên \(R(A,B,C)\), nghiệp vụ khẳng định \(A\twoheadrightarrow B\). Có thể phân rã lossless thành những quan hệ nào?

**Lời giải:** Theo tương đương giữa MVD và JD hai phép chiếu, có \(*\{AB,AC\}\); do đó phân rã thành `R1(A,B)`, `R2(A,C)` là **nối không mất mát**. Điều này không có nghĩa \(A\rightarrow B\); một \(A\) vẫn có thể có nhiều \(B\).

### Bài 4 — Kiểm tra 5NF

Cho `PERMISSION(S,P,J)`, chỉ có khóa ứng viên `(S,P,J)` theo các FD được xác nhận, và JD không tầm thường \(*\{SP,SJ,PJ\}\) đúng theo nghiệp vụ.

**Lời giải:** JD này **không được suy ra chỉ từ khóa `SPJ`**, nên bảng chưa đạt **5NF**. Có thể tách thành `SP`, `SJ`, `PJ` theo JD đã xác nhận. Không kết luận như vậy với bảng hợp đồng thực tế nếu JD không đúng.

### Bài 5 — Lossless nhưng không bảo toàn FD

Cho \(R(A,B,C)\), \(F=\{AB\rightarrow C,\ C\rightarrow B\}\), tách thành `R1(C,B)` và `R2(A,C)`. Phân rã có lossless không? Có bảo toàn `AB → C` không?

**Lời giải:** **Lossless**, vì `C` là giao của hai bảng và `C → B`. **Không bảo toàn `AB → C`** chỉ bằng phụ thuộc cục bộ trên từng bảng; ví dụ `R1={(c1,b1),(c2,b1)}`, `R2={(a1,c1),(a1,c2)}` tạo hai bộ cùng `(a1,b1)` nhưng khác `C`.

### Bài 6 — Thời gian hiệu lực

Một nhà cung cấp được duyệt linh kiện `P1` vào tháng 1, được duyệt cho dự án `J1` vào tháng 2, còn dự án chỉ cho dùng `P1` trong tháng 3. Có thể nối ba bản ghi phê duyệt theo mã và khẳng định quyền cung cấp tại một thời điểm không?

**Lời giải:** Không. Các phê duyệt chưa chắc **cùng có hiệu lực tại một thời điểm**. Cần mô hình khoảng thời gian hiệu lực, hoặc quy tắc xác định thời điểm kiểm tra; JD chỉ theo ba mã không đủ diễn đạt điều kiện thời gian này.

### Bài 7 — Dữ liệu mẫu không sinh bộ giả

Một bảng `R(S,P,J)` chỉ có một bộ ba, và khi chiếu thành `SP`, `SJ`, `PJ` rồi nối lại vẫn chỉ có một bộ. Có thể kết luận JD luôn đúng không?

**Lời giải:** Không. Một dòng dữ liệu thỏa rất nhiều phụ thuộc tình cờ. Muốn kết luận JD là ràng buộc của lược đồ, phải xác nhận rằng **mọi bộ ba có đủ ba cặp đều bắt buộc tồn tại** trên mọi trạng thái hợp lệ.

## 16. Checklist trước khi phân rã thành nhiều quan hệ

- [ ] Đã định nghĩa chính xác mỗi dòng là **quyền**, **sự kiện**, **hợp đồng** hay **bản ghi lịch sử**.
- [ ] Đã xác nhận JD với **tập thuộc tính của từng phép chiếu**, không chỉ dựa trên dữ liệu mẫu.
- [ ] Đã thử tình huống các cặp cùng tồn tại nhưng bộ ba thực tế chưa có.
- [ ] Đã chứng minh phép phân rã **nối không mất mát** theo các ràng buộc nghiệp vụ.
- [ ] Đã kiểm tra **bảo toàn phụ thuộc** độc lập với tính lossless.
- [ ] Đã phân biệt FD, MVD hai phép chiếu và JD tổng quát.
- [ ] Đã đánh giá liệu có JD không tầm thường **không suy ra từ các khóa ứng viên** trước khi kết luận đạt 5NF.
- [ ] Đã thiết kế khóa, khóa ngoại và cơ chế kiểm soát các ràng buộc liên bảng khi cần.
- [ ] Đã xem xét thời gian hiệu lực, dữ liệu trùng, `NULL`, chỉ mục và số bộ trung gian khi join.
- [ ] Đã kiểm thử truy vấn theo đúng mức hạt để tránh nhân số lượng, doanh thu hoặc tạo sự kiện giả.

**Ghi nhớ:** **Phụ thuộc nối** nói rằng một quan hệ có thể được tái tạo **chính xác từ nhiều phép chiếu**. Khi nghiệp vụ thật sự quy định các tổ hợp được quyết định hoàn toàn bởi những quan hệ cặp, phân rã có thể loại dư thừa và hỗ trợ 5NF. Khi bộ ba mang ý nghĩa sự kiện riêng, phép nối các cặp có thể tạo dữ liệu giả. Quy tắc nghiệp vụ và chứng minh **nối không mất mát** phải đi trước quyết định tách bảng.

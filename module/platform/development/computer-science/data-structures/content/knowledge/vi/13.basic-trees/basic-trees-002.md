# Gốc, nút cha, nút con, anh em, lá và nút trong

## 1. Vì sao cần gọi tên chính xác các vị trí trong cây?

**Cây (tree)** là cấu trúc dữ liệu mô tả quan hệ phân cấp. Ta gặp cây trong hệ thống thư mục, danh mục sản phẩm, sơ đồ tổ chức, cây phân tích biểu thức, cây tìm kiếm và nhiều thuật toán trên đồ thị.

Trong chương **Cây cơ bản** của học phần **Cấu trúc dữ liệu**, sáu khái niệm quan trọng nhất khi xem một cây theo quan hệ phân cấp là:

- **Gốc (root):** nút đứng đầu cây.
- **Nút cha (parent):** nút ngay phía trên một nút.
- **Nút con (child):** nút nằm ngay phía dưới nút cha.
- **Anh em (siblings):** những nút khác nhau có cùng một cha.
- **Lá (leaf):** nút không có con.
- **Nút trong (internal node):** nút có ít nhất một con.

Những thuật ngữ này không chỉ để mô tả hình vẽ. Chúng quyết định thuật toán sẽ đi từ đâu, lưu các liên kết như thế nào, điều kiện dừng khi duyệt và cập nhật cây, cũng như cách phân tích **bất biến, thời gian và bộ nhớ** để chọn cấu trúc phù hợp.

Chẳng hạn, một hàm xóa **lá** chỉ cần loại một nút không có con, trong khi việc xóa **nút trong** có thể ảnh hưởng tới cả cây con bên dưới. Một thuật toán tìm **cha** thường khác với thuật toán liệt kê toàn bộ **hậu duệ**; thiết kế lưu trữ phải phục vụ đúng nhu cầu đó.

### Trước hết: cây có gốc là gì?

Một **cây vô hướng** là một đồ thị liên thông, không có chu trình. Khi chọn một nút làm **gốc**, ta có **cây có gốc (rooted tree)**. Từ gốc, mỗi cạnh được hiểu theo chiều từ **cha xuống con**.

Trong một cây có gốc hợp lệ, ta giả định:

1. Cây có ít nhất một nút; trường hợp cấu trúc rỗng được xử lý riêng trong API.
2. Có đúng **một gốc**.
3. Gốc **không có cha**.
4. Mọi nút khác có **đúng một cha**.
5. Mỗi nút đều thuộc cùng cây và có thể đi tới từ gốc theo quan hệ cha–con.
6. Không có chu trình cha–con.

Với `n ≥ 1` nút, số cạnh cha–con là **`n - 1`**. Đây sẽ là một bất biến quan trọng khi cài đặt và kiểm tra cấu trúc.

## 2. Một cây mẫu để theo dõi mọi khái niệm

Xét cây phân cấp sau:

```text
                     R
                 /   |   \
                A    B    C
               / \    \
              D   E    F
                  |
                  G

Gốc: R
Cạnh cha–con:
R–A, R–B, R–C, A–D, A–E, B–F, E–G
```

Có tổng cộng **8 nút**: `R, A, B, C, D, E, F, G`, và **7 cạnh**. Trong hình, các cạnh biểu diễn quan hệ từ nút phía trên tới nút phía dưới.

Ta có thể đọc cây thành các câu:

- `R` là **gốc**.
- `R` là **cha** của `A, B, C`; ngược lại `A, B, C` là **con** của `R`.
- `A, B, C` là **anh em** của nhau vì cùng cha `R`.
- `D` và `E` là anh em vì cùng cha `A`.
- `C, D, F, G` là các **lá** vì không có con.
- `R, A, B, E` là các **nút trong** vì mỗi nút có ít nhất một con.

Dù `B` chỉ có một con là `F`, `B` vẫn là **nút trong**. Dù `C` nằm ngay ở mức thứ hai của hình, `C` vẫn là **lá** vì không có con. Việc một nút là lá hay nút trong **không phụ thuộc vào nó được vẽ ở hàng cao hay thấp**, mà phụ thuộc vào số con hiện có.

### Bảng quan hệ đầy đủ

| Nút | Cha trực tiếp | Danh sách con trực tiếp | Loại nút |
|---|---|---|---|
| `R` | Không có | `A, B, C` | Gốc, nút trong |
| `A` | `R` | `D, E` | Nút trong |
| `B` | `R` | `F` | Nút trong |
| `C` | `R` | Rỗng | Lá |
| `D` | `A` | Rỗng | Lá |
| `E` | `A` | `G` | Nút trong |
| `F` | `B` | Rỗng | Lá |
| `G` | `E` | Rỗng | Lá |

Bảng cho thấy một nút có thể đồng thời mang **nhiều vai trò** ở những nhóm khái niệm khác nhau. Chẳng hạn, `A` vừa là con của `R`, vừa là cha của `D, E`, vừa là anh em của `B, C`, vừa là nút trong. Riêng **lá** và **nút trong** loại trừ nhau theo quy ước “có con hay không có con”.

## 3. Gốc (root): điểm bắt đầu của quan hệ phân cấp

**Gốc** là nút được chọn làm điểm khởi đầu của cấu trúc phân cấp. Đặc điểm:

- **Không có cha** trong cây.
- Nếu cây có `n > 1` nút, gốc phải có ít nhất một con vì toàn bộ cây liên thông.
- Nếu cây chỉ có **một nút**, chính nút đó là gốc **và cũng là lá**.
- Khi tính độ sâu theo số cạnh, **độ sâu của gốc bằng `0`**.

Ví dụ với cây mẫu, gốc là `R`. Từ `R` ta có thể duyệt tới mọi nút còn lại bằng các cạnh cha–con.

### Gốc là thuộc tính của cách nhìn, không phải mọi đồ thị đều có sẵn gốc

Về mặt đồ thị vô hướng, cấu trúc cây mẫu không cần phân biệt đỉnh `R`. Ta có thể chọn `D` làm gốc mới; khi đó `A` trở thành con của `D` và `R` trở thành con của `A` trên đường đi tương ứng.

Điều **không thay đổi** khi chọn gốc khác: tập đỉnh, tập cạnh, liên thông và tính không có chu trình.

Điều **có thể thay đổi**: ai là cha, ai là con, các nhóm anh em, lá theo định nghĩa **không có con**, độ sâu và chiều cao của mỗi nút. Một đỉnh là lá theo gốc này có thể thành nút trong theo gốc khác.

**Lưu ý:** nếu cấu trúc gắn với một ý nghĩa nghiệp vụ như “thư mục gốc của dự án”, không thể tùy ý đổi gốc mà vẫn giữ nguyên ngữ nghĩa của quan hệ chứa. Việc đổi gốc là một phép biến đổi mô hình có thể hợp lệ về mặt toán học nhưng không nhất thiết hợp lệ về mặt ứng dụng.

## 4. Nút cha (parent) và nút con (child)

### 4.1. Cha và con là quan hệ **trực tiếp**

Nếu có cạnh cha–con từ `u` tới `v` theo hướng từ gốc xuống, ta nói:

- `u` là **cha trực tiếp** của `v`.
- `v` là **con trực tiếp** của `u`.

Trong cây mẫu:

```text
R → A → E → G
```

- Cha của `A` là `R`.
- Cha của `E` là `A`.
- Cha của `G` là `E`.
- `R` **không phải cha trực tiếp** của `G`; `R` là **tổ tiên** của `G`.

Phân biệt “cha” với “tổ tiên” rất quan trọng. Hàm `parent(G)` phải trả `E`, không phải `A` hay `R`. Muốn tìm tất cả tổ tiên, cần đi ngược liên tục theo liên kết cha.

### 4.2. Mỗi nút có bao nhiêu cha và bao nhiêu con?

Trong một cây có gốc:

- Gốc có **0 cha**.
- Mọi nút khác có **đúng 1 cha**.
- Một nút có thể có **0, 1, 2 hoặc nhiều con** nếu đây là **cây tổng quát**.
- **Cây nhị phân (binary tree)** là trường hợp có ràng buộc thêm: mỗi nút có tối đa **2 con**, thường được phân biệt thành con trái và con phải.

Ví dụ, `R` có ba con nên cây mẫu không phải cây nhị phân dưới biểu diễn hiện tại. Việc cây có thể vẽ với các nhánh bên trái và bên phải không tự động biến nó thành cây nhị phân.

### 4.3. Số con và danh sách con

Gọi `children(u)` là tập hoặc danh sách các con trực tiếp của `u`. **Số con** của nút `u` là:

\[
\operatorname{childCount}(u) = |\operatorname{children}(u)|.
\]

Trong cây mẫu:

- `childCount(R) = 3`.
- `childCount(A) = 2`.
- `childCount(B) = 1`.
- `childCount(C) = 0`.

Nếu lưu danh sách con trong mảng hoặc danh sách liên kết, việc **liệt kê tất cả con** của `u` tốn thời gian tỷ lệ với số con đó. Nếu cần truy vấn `childCount(u)` nhanh, có thể lưu độ dài danh sách hoặc một bộ đếm được cập nhật nhất quán.

### 4.4. Cây có thứ tự và cây không có thứ tự

Trong nhiều ứng dụng, **thứ tự các con** có ý nghĩa:

- Với cây phân tích biểu thức, “toán hạng trái” và “toán hạng phải” có vai trò khác nhau.
- Với mục lục, thứ tự các đề mục cần được giữ.
- Với menu, các mục có thể được sắp theo thứ tự hiển thị.

Ta gọi đó là **cây có thứ tự (ordered tree)**. Tuy nhiên, trong cây đồ thị tổng quát, việc `R` có các con `A, B, C` **không tự động có nghĩa** `A` là “con đầu tiên” theo một thứ tự được quy định. Thứ tự chỉ xuất hiện nếu mô hình hoặc cách lưu trữ định nghĩa nó.

Bài này sử dụng `list` Python để lưu `children`, nên **thứ tự được biểu diễn rõ** theo lúc thêm con. Nếu ứng dụng chỉ quan tâm tập con, có thể chọn cách lưu khác nhưng vẫn phải giữ bất biến mỗi con có đúng một cha.

## 5. Anh em (siblings): cùng cha, không phải cùng mức

Hai nút phân biệt `u` và `v` là **anh em** khi và chỉ khi:

\[
u \ne v \quad\text{và}\quad \operatorname{parent}(u)=\operatorname{parent}(v)\ne\text{None}.
\]

Điều kiện `u ≠ v` bảo đảm một nút không tự là anh em của chính nó. Điều kiện cha khác `None` giúp loại gốc ra khỏi quan hệ này.

Trong cây mẫu:

- `A, B, C` cùng là con của `R` nên là anh em.
- `D` và `E` cùng là con của `A` nên là anh em.
- `F` chỉ là con duy nhất của `B`, nên **không có anh em**.
- `R` không có cha, nên **không có anh em**.

### Cùng độ sâu chưa chắc là anh em

Ví dụ, `D`, `E` và `F` đều có độ sâu bằng `2` tính từ `R`. Nhưng:

- `D` và `E` có cùng cha `A` nên là anh em.
- `F` có cha `B` nên **không phải anh em** của `D` hoặc `E`.

Vì thế, **cùng cha** là điều kiện xác định anh em, không phải cùng hàng trên sơ đồ hay cùng độ sâu.

Nếu một nút `u` có cha `p`, số anh em của nó là:

\[
\operatorname{siblingCount}(u)
= |\operatorname{children}(p)|-1.
\]

Nếu `u` là gốc, số anh em bằng `0` theo quy ước bài này.

### Anh em khác anh em liền kề

Trong một **cây có thứ tự**, ta còn có thể hỏi “anh em đứng ngay trước” hoặc “anh em đứng ngay sau” một nút trong danh sách con của cha. Đây là quan hệ **có tính thứ tự**, khác với quan hệ anh em nói chung.

Với các con `[A, B, C]` của `R`, `A` và `C` vẫn là anh em dù không đứng cạnh nhau trong danh sách. `B` là anh em liền trước của `C` nếu thứ tự đang xét là `A, B, C`.

## 6. Lá (leaf): nút không có con

Trong **cây có gốc**, một **lá** là nút có **0 con**:

\[
\operatorname{isLeaf}(u)
\iff |\operatorname{children}(u)|=0.
\]

Ở cây mẫu, tập lá là:

\[
L=\{C,D,F,G\}.
\]

Điều cần chú ý:

- `C` là lá dù nối trực tiếp với gốc.
- `G` là lá dù nằm sâu hơn các nút khác.
- `F` là lá dù cha của nó chỉ có một con.
- Lá không có nghĩa “nút nằm ở độ sâu lớn nhất của toàn bộ cây”. Các lá có thể ở **nhiều độ sâu khác nhau**.

### Trường hợp một nút

```text
      R
```

Khi cây có một nút duy nhất, `R` là **gốc**, đồng thời là **lá** vì không có con. Nó **không phải nút trong** theo định nghĩa của bài.

Đây là trường hợp biên quan trọng. Nếu viết `is_leaf(root) = False` chỉ vì đó là gốc thì sẽ sai đối với cây một nút.

### Vì sao lá thường là điểm dừng của thuật toán?

Nhiều thuật toán phân rã cây xử lý các cây con. Khi gặp lá, không còn lời gọi tới con nên quá trình đi xuống dừng lại. Ví dụ, tính số lá:

```text
COUNT_LEAVES(u):
    if u không có con:
        return 1

    total = 0
    for mỗi con v của u:
        total += COUNT_LEAVES(v)
    return total
```

Trong một cây hữu hạn hợp lệ, việc đi xuống liên tục cuối cùng sẽ gặp lá. Đây là một cơ sở để lập luận đệ quy kết thúc.

**Lưu ý:** một hàm xử lý cây rỗng có thể dùng `root is None` làm base case riêng; `None` không phải một lá thực sự của cây.

## 7. Nút trong (internal node): nút có ít nhất một con

Một **nút trong** là nút có **ít nhất một con**:

\[
\operatorname{isInternal}(u)
\iff |\operatorname{children}(u)|>0.
\]

Trong cây mẫu:

\[
I=\{R,A,B,E\}.
\]

Vì thế:

- `R` là gốc **và** nút trong.
- `B` là nút trong dù chỉ có một con.
- `E` là nút trong vì có con `G`.
- `C, D, F, G` không phải nút trong.

Với **cây có gốc không rỗng**, mọi nút thuộc đúng một trong hai nhóm: **lá** hoặc **nút trong**. Nếu `n` là số nút, `L` là số lá và `I` là số nút trong:

\[
n=L+I.
\]

Ở ví dụ, `n=8`, `L=4` và `I=4`, nên `8=4+4`.

### Nút trong không đồng nghĩa “nút có ít nhất hai con”

Định nghĩa “nút trong” chỉ yêu cầu **một con trở lên**. Nếu `A → B → C` là cây đường thẳng gốc `A` thì `A` và `B` đều là nút trong; `C` là lá.

Một số bài toán riêng về **cây nhị phân đầy đủ** quy định nút trong có đúng hai con. Đó là **ràng buộc của loại cây đặc biệt**, không phải định nghĩa chung của nút trong.

## 8. Đừng nhầm “lá có gốc” với “đỉnh bậc một” của cây vô hướng

Trong **đồ thị vô hướng**, **bậc (degree)** của đỉnh là số cạnh kề với nó. Với cây có gốc, ta có quan hệ:

\[
\deg(u)=
\begin{cases}
|\operatorname{children}(u)|, & u\text{ là gốc},\\
|\operatorname{children}(u)|+1, & u\text{ không phải gốc}.
\end{cases}
\]

Nguyên nhân: nút không phải gốc còn có một cạnh nối tới **cha**.

Ví dụ:

| Nút | Số con | Bậc vô hướng | Vai trò trong cây gốc `R` |
|---|---:|---:|---|
| `R` | 3 | 3 | Gốc, nút trong |
| `B` | 1 | 2 | Nút trong |
| `C` | 0 | 1 | Lá |
| `E` | 1 | 2 | Nút trong |
| `G` | 0 | 1 | Lá |

Trong một cây vô hướng có ít nhất hai đỉnh, người ta thường gọi **đỉnh bậc `1`** là lá của cây vô hướng. Với cây có gốc, định nghĩa **lá = không có con** được ưu tiên sử dụng trong bài này.

Điều khác biệt xuất hiện nếu chọn một đỉnh bậc `1` làm gốc. Ví dụ chọn `C` làm gốc mới:

- `C` có **một con** (đỉnh `R`) nên `C` trở thành **nút trong** theo quan hệ có gốc.
- Tuy nhiên bậc vô hướng của `C` vẫn là `1`.

Đây không phải mâu thuẫn: hai thuật ngữ được xác định trong **hai cách nhìn** khác nhau. Trường hợp cây chỉ có một đỉnh càng cho thấy sự cần thiết của quy ước: bậc vô hướng của gốc là `0`, nhưng theo định nghĩa không có con thì nó vẫn là lá của cây có gốc.

## 9. Các quan hệ mở rộng: tổ tiên, hậu duệ, độ sâu và cây con

Sáu khái niệm chính thường được dùng cùng những quan hệ gần gũi.

### Tổ tiên và hậu duệ

Nếu đi theo liên kết cha từ nút `u` về gốc, các nút gặp được (không tính `u`) là **tổ tiên (ancestors)** của `u`. Ngược lại, các nút thuộc phía dưới `u` theo cạnh cha–con là **hậu duệ (descendants)** của nó.

Với cây mẫu:

- Tổ tiên của `G` là `E, A, R`, theo thứ tự từ gần tới xa.
- Hậu duệ của `A` là `D, E, G`.
- `A` không phải cha trực tiếp của `G`, nhưng là tổ tiên của `G`.

Ở đây quy ước **không tính chính nút đang xét** là tổ tiên hoặc hậu duệ của nó. Một số tài liệu định nghĩa quan hệ bao gồm cả chính nút; khi dùng thuật toán phải nêu rõ quy ước.

### Cây con (subtree)

**Cây con có gốc tại `u`** gồm chính `u` và tất cả hậu duệ của `u`.

```text
Cây con tại A:

      A
     / \
    D   E
        |
        G
```

Nó có bốn nút `A, D, E, G` và ba cạnh. Nếu tách cây con này khỏi phần còn lại bằng cách bỏ cạnh `R—A`, ta thu được một thành phần có gốc riêng `A`; đồng thời phần cây còn lại vẫn là một cây khác. Toàn bộ cấu trúc lúc đó trở thành **rừng** gồm hai cây, không còn một cây duy nhất.

### Độ sâu và chiều cao

Theo quy ước đếm **số cạnh**:

- **Độ sâu (depth)** của `u` là số cạnh trên đường từ gốc tới `u`.
- **Chiều cao (height)** của `u` là số cạnh trên đường đi dài nhất từ `u` xuống một lá trong cây con của `u`.

Với cây mẫu:

| Nút | Độ sâu | Chiều cao |
|---|---:|---:|
| `R` | 0 | 3 |
| `A` | 1 | 2 |
| `B` | 1 | 1 |
| `C` | 1 | 0 |
| `D` | 2 | 0 |
| `E` | 2 | 1 |
| `F` | 2 | 0 |
| `G` | 3 | 0 |

Chiều cao của cả cây là chiều cao của gốc: `height(R)=3`. **Lá luôn có chiều cao `0`** theo quy ước này, nhưng độ sâu các lá không nhất thiết giống nhau.

## 10. Những bất biến quan trọng của cây có gốc

Giả sử `n ≥ 1` là tổng số nút và mọi nút đều có một danh sách con.

### 10.1. Bất biến liên kết cha–con hai chiều

Nếu mỗi nút `v` có một trường `parent` và mỗi nút `u` có danh sách `children`, thì hai dạng tham chiếu phải nhất quán:

> `v` nằm trong `children[u]` khi và chỉ khi `parent[v] is u`.

Ngoài ra:

- Không có một nút con xuất hiện **hai lần** trong cùng danh sách con.
- Không có một nút làm con của **hai cha khác nhau**.
- Không được có liên kết `u → u` hay chu trình cha–con.
- Chỉ một nút có `parent = None` nếu đang biểu diễn một cây không rỗng duy nhất.

Đây là các bất biến cần kiểm tra khi thêm, xóa hoặc chuyển nút.

### 10.2. Tổng số con bằng số cạnh

Mỗi nút không phải gốc đóng góp **một cạnh từ cha đến nó**. Vì cây có `n - 1` nút không phải gốc:

\[
\sum_{u\in V}|\operatorname{children}(u)|=n-1.
\]

Trong cây mẫu, các nút trong có số con lần lượt `3,2,1,1`, còn các lá có `0` con:

\[
3+2+1+1+0+0+0+0=7=8-1.
\]

Đẳng thức này hữu ích để kiểm tra số liên kết cha–con trong một cấu trúc đã được xác nhận là cây.

**Nhưng chỉ đếm đủ `n - 1` liên kết chưa chứng minh cấu trúc hợp lệ.** Ví dụ có thể vừa tồn tại một chu trình ở một nhóm nút, vừa có một nút bị cô lập. Phải kiểm tra thêm **không có chu trình** và **tất cả nút đều nối tới cùng gốc**.

### 10.3. Luôn tồn tại ít nhất một lá

Trong cây có gốc hữu hạn và không rỗng, bắt đầu từ gốc rồi đi xuống một nút con bất kỳ nếu còn con. Vì cây hữu hạn và không có chu trình, không thể đi xuống mãi; cuối cùng phải dừng ở một nút **không có con**. Vậy luôn tồn tại ít nhất **một lá**.

Cây có một nút đạt đúng một lá. Cây dạng chuỗi `R → A → B → C` cũng chỉ có **một lá** theo định nghĩa có gốc: nút cuối `C`.

### 10.4. Quan hệ với cây nhị phân đầy đủ

Nếu cây nhị phân **không rỗng** có quy tắc **mỗi nút trong có đúng hai con**, gọi `I` là số nút trong và `L` là số lá, ta có:

\[
n=I+L,\qquad n-1=2I.
\]

Suy ra:

\[
L=I+1.
\]

Đây là tính chất của loại cây nhị phân đầy đủ này, **không áp dụng cho mọi cây tổng quát**. Ví dụ cây `R → A → B` có hai nút trong và một lá, nên không thỏa `L=I+1`.

## 11. Cài đặt Python: cây tổng quát với liên kết cha và danh sách con

Ta dùng một lớp `TreeNode` lưu:

- `value`: dữ liệu của nút.
- `parent`: cha trực tiếp, hoặc `None` nếu là gốc của cấu trúc hiện tại.
- `children`: danh sách các nút con trực tiếp.

Để dễ hiểu, ví dụ giả định **một nút chỉ thuộc một cây tại một thời điểm**, các nút không được sửa trực tiếp trường `parent` hoặc danh sách `children` từ bên ngoài API.

### Xây lớp và các thao tác cơ bản

```python
class TreeNode:
    def __init__(self, value):
        self.value = value
        self.parent = None
        self.children = []

    def add_child(self, child):
        if not isinstance(child, TreeNode):
            raise TypeError("child phải là TreeNode")

        if child.parent is not None:
            raise ValueError("child đã có cha")

        # Không được gắn một nút vào chính nó hoặc hậu duệ của nó.
        cursor = self
        while cursor is not None:
            if cursor is child:
                raise ValueError("thao tác tạo chu trình")
            cursor = cursor.parent

        self.children.append(child)
        child.parent = self

    def is_leaf(self):
        return len(self.children) == 0

    def is_internal(self):
        return len(self.children) > 0

    def is_root(self):
        return self.parent is None

    def child_count(self):
        return len(self.children)

    def siblings(self):
        if self.parent is None:
            return []

        return [
            other
            for other in self.parent.children
            if other is not self
        ]

    def depth(self):
        result = 0
        cursor = self
        while cursor.parent is not None:
            result += 1
            cursor = cursor.parent
        return result


# Dựng cây mẫu bằng một API thống nhất.
nodes = {
    value: TreeNode(value)
    for value in "RABCDEFG"
}

nodes["R"].add_child(nodes["A"])
nodes["R"].add_child(nodes["B"])
nodes["R"].add_child(nodes["C"])
nodes["A"].add_child(nodes["D"])
nodes["A"].add_child(nodes["E"])
nodes["B"].add_child(nodes["F"])
nodes["E"].add_child(nodes["G"])

root = nodes["R"]

print(root.is_root())                      # True
print(root.child_count())                  # 3
print(nodes["E"].parent.value)             # A
print([n.value for n in nodes["D"].siblings()])  # ['E']
print(nodes["C"].is_leaf())                # True
print(nodes["B"].is_internal())            # True
print(nodes["G"].depth())                  # 3
```

Trong code, hàm `add_child` kiểm tra hai điều kiện quan trọng:

1. **Không gắn một nút đã có cha** sang cha thứ hai; muốn chuyển cây con phải có một thao tác *reparent* riêng, cập nhật cả liên kết cũ và mới.
2. **Không tạo chu trình:** trước khi gắn `child` vào `self`, duyệt từ `self` ngược qua các cha. Nếu gặp chính `child`, nghĩa là `self` nằm trong cây con của `child`; việc gắn sẽ tạo vòng.

Ví dụ, sau khi dựng cây trên:

```python
try:
    nodes["G"].add_child(nodes["R"])
except ValueError as error:
    print(error)  # thao tác tạo chu trình


try:
    nodes["C"].add_child(nodes["D"])
except ValueError as error:
    print(error)  # child đã có cha
```

**Phạm vi của lớp minh họa:** đây là cấu trúc dữ liệu dùng để học; các trường vẫn truy cập được trực tiếp trong Python. Nếu mã khác tự sửa `node.parent` hoặc `node.children`, bất biến có thể bị phá. Một thư viện thực tế nên đóng gói chặt hơn, định nghĩa rõ thay đổi cấu trúc và, nếu có nhiều luồng, dùng cơ chế đồng bộ phù hợp.

## 12. Duyệt cây để đếm lá, nút trong và quan sát quan hệ

Chúng ta có thể dùng **DFS với stack tường minh** để duyệt cây từ gốc. Vì mỗi nút của cây có gốc hợp lệ có đúng một đường đi từ gốc, mỗi nút sẽ được đưa vào stack đúng một lần.

### Đếm tổng nút, lá và nút trong

```python
def count_node_kinds(root):
    if root is None:
        return {
            "nodes": 0,
            "leaves": 0,
            "internal": 0,
        }

    pending = [root]
    total = 0
    leaves = 0
    internal = 0

    while pending:
        node = pending.pop()
        total += 1

        if node.is_leaf():
            leaves += 1
        else:
            internal += 1

        for child in node.children:
            pending.append(child)

    return {
        "nodes": total,
        "leaves": leaves,
        "internal": internal,
    }


print(count_node_kinds(root))
# {'nodes': 8, 'leaves': 4, 'internal': 4}

print(count_node_kinds(TreeNode("only")))
# {'nodes': 1, 'leaves': 1, 'internal': 0}

print(count_node_kinds(None))
# {'nodes': 0, 'leaves': 0, 'internal': 0}
```

Trong vòng lặp, **mỗi nút hoặc là lá hoặc là nút trong**, nên luôn có `total = leaves + internal` với đầu vào hợp lệ.

### Liệt kê trước cha rồi tới các con (preorder)

```python
def preorder_values(root):
    if root is None:
        return []

    result = []
    pending = [root]

    while pending:
        node = pending.pop()
        result.append(node.value)

        # Stack LIFO: đưa con vào theo thứ tự ngược.
        for child in reversed(node.children):
            pending.append(child)

    return result


print(preorder_values(root))
# ['R', 'A', 'D', 'E', 'G', 'B', 'F', 'C']
```

Do cấu trúc này lưu danh sách con theo thứ tự `A, B, C`, preorder xử lý `A` trước `B` rồi mới `C`. Với stack LIFO, ta phải **push các con theo thứ tự ngược** để phần tử con muốn xử lý trước nằm trên đỉnh.

Nếu thứ tự con không mang ý nghĩa ứng dụng, các thứ tự duyệt khác nhau vẫn có thể hợp lệ, miễn đều thăm đúng những nút thuộc cây.

### Tìm đường từ nút về gốc

Nhờ liên kết `parent`, ta có thể đi ngược từ một nút tới gốc:

```python
def path_to_root(node):
    result = []
    cursor = node

    while cursor is not None:
        result.append(cursor.value)
        cursor = cursor.parent

    return result


print(path_to_root(nodes["G"]))
# ['G', 'E', 'A', 'R']
```

Trình tự này bao gồm chính nút bắt đầu và gốc. Nếu chỉ cần **tổ tiên**, bỏ phần tử đầu tiên `G` khỏi danh sách.

## 13. Cập nhật liên kết: gắn lá, chuyển cây con và xóa

### 13.1. Thêm lá mới

Giả sử muốn thêm `H` làm con của `C`:

```python
new_leaf = TreeNode("H")
nodes["C"].add_child(new_leaf)

print(nodes["C"].is_leaf())     # False
print(nodes["C"].is_internal()) # True
print(new_leaf.parent.value)    # C
```

Trước khi thêm `H`, `C` là lá. Sau thao tác, `C` có một con nên trở thành nút trong; `H` là lá. Tổng số nút và cạnh đều tăng một, vì vậy vẫn thỏa `|E| = |V| - 1`.

Nếu thêm con vào một nút vốn đã là nút trong, nút đó vẫn thuộc nhóm nút trong. Lúc này chỉ tăng tổng nút và tổng lá thêm một, còn số nút trong không đổi.

### 13.2. Tháo một cây con thành cây riêng

Nếu muốn tách nút `u` cùng tất cả hậu duệ của nó ra thành một cây độc lập, về mặt cấu trúc có thể:

1. Xác định cha cũ `p` của `u`.
2. Xóa `u` khỏi `children[p]`.
3. Đặt `parent[u] = None`.
4. Giữ nguyên các liên kết giữa `u` và hậu duệ trong cây con.

Ví dụ mã minh họa:

```python
def detach_subtree(node):
    if node.parent is None:
        raise ValueError("nút đã là gốc, không có cha để tháo")

    old_parent = node.parent
    old_parent.children.remove(node)
    node.parent = None

    return node
```

Nếu tháo cây con gốc `E` khỏi `A`, nhóm `E, G` trở thành một cây có gốc riêng `E`; phần cây còn lại có gốc `R`. Toàn bộ tập nút lúc này gồm **hai cây**, tức là một **rừng**, không phải một cây duy nhất. Nếu `E` là con cuối của `A`, nút `A` có thể chuyển từ nút trong thành lá.

### 13.3. Đổi cha (reparent) không được tạo chu trình

Muốn chuyển cây con của `u` sang cha mới `v` trong cùng một cây, phải xác định `v` **không nằm trong cây con của `u`**. Nếu chọn một hậu duệ làm cha mới, các liên kết cha–con sẽ tạo vòng.

Thao tác đổi cha cần kiểm tra trước và cập nhật nhất quán:

- Xóa liên kết với cha cũ.
- Gắn `u` vào danh sách con của cha mới.
- Đặt `parent[u]` thành cha mới.
- Cập nhật các giá trị phụ thuộc cấu trúc như độ sâu, chiều cao hoặc kích thước cây con nếu ứng dụng lưu chúng.

Nếu giữ nguyên tổng số nút và chuyển đúng một cạnh nối cây con vào vị trí hợp lệ trong cùng cây, số cạnh vẫn bằng `n - 1`. Nhưng **chỉ dựa vào số cạnh là không đủ**: quan hệ cha, tính liên thông và không chu trình vẫn phải đúng.

Trong ví dụ Python, thao tác `add_child` **cố ý không tự reparent**; điều đó giúp API đơn giản và tránh việc âm thầm xóa quan hệ cũ.

## 14. Phân tích thời gian và bộ nhớ của các thao tác

Gọi:

- `n` là tổng số nút trong cây.
- `h` là chiều cao của cây tính theo **số cạnh**.
- `k` là số con trực tiếp của một nút.
- Giả định tra cứu đối tượng nút đã có tham chiếu; nếu phải tìm nút theo giá trị trong toàn cây, có thể cần thời gian khác.

| Thao tác | Thời gian thông thường | Giải thích |
|---|---|---|
| `is_root()` | `O(1)` | Chỉ kiểm tra `parent is None` |
| `is_leaf()` / `is_internal()` | `O(1)` | Kiểm tra độ dài danh sách con |
| `child_count()` | `O(1)` | `len(children)` của Python |
| Xem cha trực tiếp | `O(1)` | Có sẵn liên kết `parent` |
| Liệt kê `k` con | `O(k)` | Phải duyệt các phần tử con |
| Tạo danh sách anh em | `O(k)` | Duyệt danh sách con của cha, loại chính nút |
| Tính độ sâu bằng cách đi theo cha | `O(h)` | Trong trường hợp xấu nhất đi qua `h` cạnh |
| Gắn `child` qua `add_child` minh họa | `O(h)` cho kiểm tra chu trình và `O(1)` amortized để append | Phải đi ngược từ cha dự kiến lên gốc |
| Tháo cây con bằng `list.remove` | `O(k)` | Phải tìm nút trong danh sách con của cha |
| Duyệt và đếm mọi loại nút | `O(n)` | Thăm mỗi nút một lần |
| Liệt kê đường từ nút về gốc | `O(h)` | Đi ngược tối đa `h` cạnh |

**Chi phí bộ nhớ:**

- Lưu `n` đối tượng nút, `n - 1` liên kết cha và `n - 1` mục trong danh sách con cần **`O(n)` bộ nhớ tổng**.
- Stack tường minh trong phép duyệt có thể cần tối đa **`O(n)` phần tử chờ**, ví dụ khi một nút có rất nhiều con được push cùng lúc.
- Hàm `count_node_kinds` dùng bộ nhớ phụ `O(n)` trong trường hợp xấu nhất; hàm `preorder_values` còn lưu `n` giá trị kết quả, nên toàn bộ bộ nhớ bổ sung cũng là `O(n)`.
- Hàm `path_to_root` giữ một danh sách đường đi dài tối đa `h+1` nút, tốn **`O(h)` bộ nhớ**.

**Phân biệt cấu trúc và dữ liệu:** `O(n)` bộ nhớ ở đây mô tả số tham chiếu và đối tượng nút, chưa tính dung lượng nội tại của `value` nếu giá trị là một tài liệu hoặc đối tượng lớn.

Nếu dùng cấu trúc cây chỉ lưu **danh sách con mà không lưu cha**, việc tìm cha của một nút bất kỳ có thể đòi hỏi duyệt từ gốc, tốn `O(n)` trong trường hợp xấu nhất. Việc thêm trường `parent` đổi một lượng bộ nhớ `O(n)` lấy truy vấn cha `O(1)`.

## 15. Khi nào nên dùng từng cách biểu diễn?

### Cây thư mục và phân cấp tổ chức

Một thư mục có thể chứa nhiều mục con; nếu quan hệ chứa là cây, mỗi mục không phải gốc có đúng một thư mục cha. Chọn `children` để liệt kê thư mục con và `parent` để di chuyển lên cấp trên.

Tuy nhiên, hệ thống tệp thực tế có thể có **liên kết tượng trưng (symlink)** hoặc cơ chế tham chiếu chéo. Nếu xét mọi liên kết như quan hệ cha–con, cấu trúc có thể không còn là cây thuần túy. Vì thế cần phân biệt “quan hệ chứa” và “quan hệ tham chiếu”.

### Menu và mục lục có thứ tự

Menu hoặc mục lục thường quan tâm cả **thứ tự các mục**. Dùng danh sách con giúp giữ thứ tự đã xác định. Các nút anh em có cùng cha, nhưng có thể đứng ở những vị trí khác nhau trong danh sách.

### Cây phân tích biểu thức

Trong cây cú pháp, các nút trong thường là **toán tử hoặc cấu trúc ngữ pháp** và lá thường là **toán hạng, hằng số hoặc định danh**, tùy cách xây cây. Đây là một **quy ước ứng dụng** chứ không phải định nghĩa của lá: nút là lá chỉ vì nó **không có con**, không phải vì kiểu dữ liệu của nó nhất định là một hằng số.

### Khi một đối tượng có nhiều cha

Nếu một mục có thể thuộc đồng thời nhiều mục cha, đó không còn là cây có gốc theo định nghĩa bài này. Cấu trúc phù hợp hơn có thể là **đồ thị có hướng không chu trình (DAG)** hoặc đồ thị tổng quát. Một DAG có thể không có chu trình có hướng nhưng vẫn cho phép **nhiều cha**, nên không được tự coi là cây.

**Nguyên tắc chọn cấu trúc:** kiểm tra ràng buộc **một gốc, một cha cho mọi nút khác và không chu trình**, thay vì chỉ nhìn sơ đồ có dạng nhiều nhánh.

## 16. Những lỗi tư duy và cài đặt thường gặp

1. **Cho rằng gốc không thể là lá.** Cây một nút có gốc đồng thời là lá.
2. **Coi mọi nút ở hàng cuối là lá và các nút ở hàng trên là nút trong.** Lá được xác định bởi **không có con**, không phải cách vẽ.
3. **Nhầm nút có một con là lá.** Chỉ cần có **một con** đã là nút trong.
4. **Dùng cùng độ sâu để kết luận là anh em.** Anh em phải có **cùng cha trực tiếp**.
5. **Nhầm cha trực tiếp với tổ tiên.** Cha là một nút ngay phía trên; tổ tiên có thể cách nhiều cạnh.
6. **Đồng nhất bậc vô hướng với số con.** Nút không phải gốc có thêm một cạnh tới cha.
7. **Cho rằng tất cả cây đều là cây nhị phân.** Cây tổng quát cho phép nút có ba hoặc nhiều con.
8. **Không kiểm tra chu trình khi gắn cây con.** Gắn tổ tiên làm con của hậu duệ tạo vòng và phá cấu trúc cây.
9. **Sửa `parent` mà quên cập nhật `children`.** Hai hướng tham chiếu phải nhất quán.
10. **Gắn một nút đã có cha vào cha khác mà không tháo liên kết cũ.** Điều đó có thể tạo hai cha cho cùng nút.
11. **Quên trường hợp API nhận cây rỗng.** Có thể dùng `root = None` làm giá trị vắng cây, nhưng `None` không phải một nút lá.
12. **Cho rằng thứ tự con là bất biến của mọi cây.** Thứ tự chỉ được bảo đảm nếu mô hình định nghĩa cây có thứ tự.
13. **Bỏ qua chi phí tìm kiếm nút.** Có sẵn tham chiếu `node` khác với việc phải tìm theo tên trên toàn cây; truy vấn thực tế có thể không còn `O(1)`.
14. **Không tách chi phí lưu cây và chi phí lưu kết quả.** DFS có thể chỉ cần stack công việc, nhưng nếu còn xây danh sách gồm toàn bộ nút thì sẽ cần thêm `O(n)` bộ nhớ.

## 17. Kiểm thử và trường hợp biên

Các đoạn sau dùng lớp `TreeNode` và các hàm đã định nghĩa trong phần trước:

```python
# Cây chỉ có một nút.
single = TreeNode("single")
assert single.is_root()
assert single.is_leaf()
assert not single.is_internal()
assert single.depth() == 0
assert single.siblings() == []

# Cây mẫu đã tạo từ trước.
assert root.child_count() == 3
assert nodes["B"].parent is root
assert nodes["D"].parent is nodes["A"]
assert nodes["D"].siblings() == [nodes["E"]]
assert nodes["F"].siblings() == []
assert nodes["G"].depth() == 3

counts = count_node_kinds(root)
# Nếu đã chạy phần 13 để thêm H thì cây có 9 nút;
# bài kiểm tra dưới đây xác minh bất biến chung cho mọi trạng thái hợp lệ.
assert counts["nodes"] == counts["leaves"] + counts["internal"]

# Xác minh thuộc tính cây khi khởi tạo hoàn toàn mới.
test_root = TreeNode("R")
test_child = TreeNode("C")
test_root.add_child(test_child)
assert test_root.is_internal()
assert test_child.is_leaf()
assert test_child.parent is test_root
```

Cần kiểm thử thêm:

- Gắn một nút làm con của chính nó.
- Gắn một tổ tiên xuống dưới hậu duệ.
- Gắn một nút đã có cha vào nút cha khác.
- Tháo lá duy nhất của một nút trong và kiểm tra nút cha có trở thành lá không.
- Chọn một gốc khác khi làm việc với cây vô hướng rồi tính lại các quan hệ cha–con.
- Tạo cây rất sâu và dùng **duyệt lặp** để tránh giới hạn đệ quy của runtime nếu dữ liệu lớn.

## 18. Bài tập thực hành có đáp án

### Bài 1. Nhận diện vai trò

Dựa trên cây mẫu `R, A, B, C, D, E, F, G`, hãy nêu gốc, toàn bộ lá và toàn bộ nút trong.

**Đáp án:** Gốc là `R`. Lá là `C, D, F, G`. Nút trong là `R, A, B, E`.

### Bài 2. Quan hệ cha và anh em

Trong cây mẫu, cha của `G` là ai? `D` có những anh em nào? `F` có phải anh em của `D` không?

**Đáp án:** Cha của `G` là `E`. Anh em của `D` là `E`. `F` không phải anh em của `D` vì cha của `F` là `B` còn cha của `D` là `A`.

### Bài 3. Cùng độ sâu

Nút `D` và `F` đều có độ sâu bằng `2` tính từ `R`. Có thể kết luận chúng là anh em không?

**Đáp án:** Không. Chúng có cha khác nhau: `D` có cha `A`, `F` có cha `B`. Cùng độ sâu không đồng nghĩa cùng cha.

### Bài 4. Cây một nút

Một cây chỉ gồm nút `X`. Hãy xác định gốc, số lá, số nút trong, số cạnh.

**Đáp án:** `X` là gốc và là lá. Có `1` lá, `0` nút trong và `0` cạnh.

### Bài 5. Nút trong có một con

Cho cây `P → Q → S`. Chọn `P` làm gốc. Nút nào là lá và nút nào là nút trong?

**Đáp án:** `S` là lá. `P` và `Q` đều là nút trong vì mỗi nút có một con.

### Bài 6. Số cạnh và tổng số con

Một cây có `12` nút. Tổng số liên kết cha–con là bao nhiêu? Tổng số con tính trên tất cả nút bằng bao nhiêu?

**Đáp án:** Cây có `12 - 1 = 11` cạnh cha–con. Mỗi nút không phải gốc được tính đúng một lần trong danh sách con của cha nên tổng số con cũng bằng `11`.

### Bài 7. Thay đổi phân loại sau khi thêm nút

Trong cây mẫu ban đầu, thêm nút `H` làm con của `C`. Số lá và số nút trong thay đổi ra sao?

**Đáp án:** Ban đầu có `4` lá và `4` nút trong. Sau khi thêm, `C` từ lá thành nút trong và `H` là lá mới: số lá vẫn **`4`**, số nút trong tăng thành **`5`**. Tổng số nút tăng từ `8` lên `9`.

### Bài 8. Tháo cây con

Trong cây mẫu ban đầu, tháo cây con có gốc `E` khỏi `A`. Có bao nhiêu cây riêng biệt? `A` có trở thành lá không?

**Đáp án:** Có **hai cây**: cây gốc `R` và cây gốc `E` chứa `G`. `A` vẫn có con `D` nên **chưa trở thành lá**.

### Bài 9. Độ sâu và chiều cao

Tính độ sâu của `G` và chiều cao của `A` theo quy ước số cạnh.

**Đáp án:** Đường `R → A → E → G` có `3` cạnh nên `depth(G)=3`. Đường dài nhất từ `A` tới lá là `A → E → G`, gồm `2` cạnh nên `height(A)=2`.

### Bài 10. Đổi gốc và bậc vô hướng

Trong cây có hai nút `U—V`, ban đầu chọn `U` làm gốc. Sau đó chọn `V` làm gốc. Loại nút của `U` có thay đổi không? Bậc vô hướng của `U` có thay đổi không?

**Đáp án:** Ban đầu `U` là gốc và là nút trong (có con `V`). Khi chọn `V` làm gốc, `U` không còn con nên là **lá**. Bậc vô hướng của `U` vẫn bằng **`1`**, vì chỉ đổi cách định gốc chứ không thay cạnh.

### Bài 11. Tính chất của cây nhị phân đầy đủ

Một cây nhị phân không rỗng có `I = 5` nút trong, mỗi nút trong đều có đúng hai con. Có bao nhiêu lá và bao nhiêu nút?

**Đáp án:** `L=I+1=6` lá. Tổng số nút `n=I+L=11`, số cạnh `n-1=10`. Kiểm tra tổng số con: `2I=10`.

## 19. Tổng kết

Trong **cây có gốc**, **gốc** là nút không có cha; mỗi nút còn lại có **đúng một cha trực tiếp**; **con** là nút nối trực tiếp phía dưới; **anh em** là các nút khác nhau có cùng cha; **lá** là nút **không có con**; **nút trong** là nút **có ít nhất một con**.

Những định nghĩa này cho phép duy trì các bất biến quan trọng: một gốc, một cha cho mỗi nút còn lại, không chu trình, liên kết cha–con nhất quán, và với cây không rỗng có `n` nút thì có **`n-1` cạnh** cùng `n=L+I`. Các khái niệm tổ tiên, hậu duệ, cây con, độ sâu và chiều cao mở rộng cách nhìn phân cấp mà không thay đổi nguyên tắc cốt lõi.

Khi cài đặt, **liên kết `parent`** giúp truy cập cha trong `O(1)`, **danh sách `children`** hỗ trợ liệt kê con, và DFS/BFS xử lý toàn bộ cây trong **`O(n)` thời gian**. Hãy luôn phân biệt cấu trúc cây tổng quát với cây nhị phân, lá theo quan hệ có gốc với bậc vô hướng, cũng như việc **sở hữu tham chiếu tới một nút** với **tìm kiếm nút theo giá trị**. Đó là cơ sở để lựa chọn và bảo vệ cấu trúc cây trong những bài toán thực tế.

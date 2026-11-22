# Loại bỏ các trạng thái đối xứng trong quay lui

## 1. Vì sao quay lui cần nhận diện đối xứng?

**Quay lui (backtracking)** duyệt một cây các quyết định, thử thêm lựa chọn, kiểm tra ràng buộc, rồi hoàn tác để khám phá nhánh khác. Nó rất hữu ích cho hoán vị, tổ hợp, N-Queens, tô màu đồ thị, phân chia tập, xếp hình và nhiều bài toán tìm kiếm tổ hợp. Nhược điểm là số nhánh có thể tăng theo hàm mũ hoặc giai thừa.

Một nguyên nhân lãng phí là **nhiều nhánh thực chất biểu diễn cùng một lời giải theo cách mà đề bài coi là tương đương**. Chẳng hạn, với các giá trị `[1,1,2]`, nếu xem hai số `1` là hai phần tử **không phân biệt bằng giá trị**, việc hoán đổi “số 1 thứ nhất” và “số 1 thứ hai” không tạo ra một hoán vị giá trị mới.

Tương tự, một cách đặt quân hậu trên bàn cờ vuông có thể được **phản chiếu hoặc quay** thành một cách đặt khác. Nếu bài yêu cầu **một đại diện của mỗi lớp đối xứng**, duyệt và giữ toàn bộ những bản sao này là không cần thiết.

**Loại bỏ trạng thái đối xứng (symmetry breaking)** nghĩa là áp đặt một quy tắc chọn **đại diện chuẩn (canonical representative)**, sao cho những trạng thái/lời giải được coi là tương đương không bị đếm hoặc xét lặp một cách vô ích.

Điều quan trọng nhất:

> **Không phải hai trạng thái trông giống nhau thì có thể gộp. Chỉ được loại bỏ khi phép biến đổi bảo toàn tính hợp lệ, mục tiêu và khái niệm “hai lời giải là một” của chính đề bài.**

Nếu đề yêu cầu **liệt kê tất cả lời giải có nhãn**, việc loại những lời giải đối xứng có thể làm mất đáp án đúng. Nếu đề yêu cầu **đếm tất cả lời giải**, việc chỉ giữ một đại diện cũng sẽ làm sai số đếm nếu không khôi phục số phần tử của mỗi lớp đối xứng.

Bài học đi từ ví dụ dễ kiểm chứng (hoán vị có giá trị lặp) đến ví dụ hình học (N-Queens), kèm một chương trình Java 17 có thể chạy được, chứng minh quy tắc loại nhánh và kiểm thử đối chứng.

## 2. Định nghĩa chính xác: phép đối xứng, quỹ đạo và đại diện chuẩn

Giả sử `S` là tập các lời giải **hợp lệ**. Một phép biến đổi `g:S\to S` là đối xứng của bài toán nếu nó ánh xạ một lời giải hợp lệ thành một lời giải hợp lệ khác, đồng thời bảo toàn những thông tin mà bài toán yêu cầu giữ.

Trong nhiều bài toán, các phép đối xứng tạo thành một **nhóm biến đổi `G`**: gồm phép đồng nhất, các phép ghép, các phép nghịch đảo và thỏa kết hợp. Chúng tác động lên `S`.

Hai lời giải `x,y` được xem là **tương đương theo đối xứng** nếu có `g\in G` sao cho:

\[
y=g(x).
\]

**Quỹ đạo (orbit)** của `x` là:

\[
\operatorname{Orb}(x)=\{g(x)\mid g\in G\}.
\]

Quỹ đạo chứa tất cả những biểu diễn có thể tạo từ `x` bằng các phép đối xứng đã được công nhận. Một đại diện chuẩn có thể là phần tử nhỏ nhất của quỹ đạo theo một thứ tự tổng xác định:

\[
\operatorname{canon}(x)
=\min_{\text{lex}}\{g(x)\mid g\in G\}.
\]

Nếu hai lời giải thuộc cùng quỹ đạo, tập biến đổi của chúng trùng nhau, nên **canonical key** cũng trùng nhau. Nếu thuộc hai quỹ đạo khác nhau và canonical key mã hóa đầy đủ trạng thái, hai khóa khác nhau.

### Phải xác định rõ đề muốn đếm cái gì

| Đầu ra đề bài yêu cầu | Được giữ một đại diện mỗi quỹ đạo? | Ghi chú |
|---|---|---|
| Chỉ kiểm tra **có tồn tại** lời giải | Có, nếu đối xứng bảo toàn tính khả thi và quy tắc không bỏ mọi đại diện | Một đại diện là đủ để chứng minh tồn tại |
| Tìm **một** lời giải tối ưu | Có, nếu đối xứng bảo toàn **giá trị mục tiêu** và giữ ít nhất một đại diện tối ưu | Không được áp dụng khi trọng số làm mất đối xứng |
| Liệt kê lời giải **khác nhau tới đối xứng** | Có | Đây chính là mục tiêu loại trùng theo quỹ đạo |
| Đếm số lớp lời giải đối xứng | Có | Đếm số canonical key khác nhau |
| Đếm **tất cả** lời giải được gắn nhãn/vị trí | Không chỉ đếm đại diện; phải tính **kích thước quỹ đạo** tương ứng | Không phải lúc nào cũng nhân đều 2, 4 hoặc 8 |
| Liệt kê **mọi** lời giải đầy đủ | Không được tự ý bỏ | Có thể sinh đại diện rồi khai triển đối xứng và loại bản sao khi cần |

Một phép đổi tên có thể là đối xứng đối với bài toán **không phân biệt nhãn**, nhưng không phải đối xứng khi đầu ra bắt buộc chứa **ID của từng đồ vật**. Một phép phản chiếu có thể hợp lệ trên bàn cờ trống, nhưng không còn hợp lệ nếu bàn cờ có vật cản lệch hoặc mỗi ô có trọng số khác nhau.

### Đối xứng, trùng lặp và trạng thái có cùng giá trị không phải một

- **Đối xứng:** tồn tại phép biến đổi hợp lệ, có nghịch đảo, bảo toàn cấu trúc bài toán.
- **Trùng đầu ra:** hai nhánh tạo ra cùng một đối tượng đáp án theo quy ước so sánh; ví dụ cùng một dãy giá trị dù chọn các chỉ số trùng giá trị theo thứ tự khác.
- **Cùng giá trị mục tiêu:** hai lời giải đều đạt điểm số `10` nhưng có thể hoàn toàn khác nhau, không có phép đối xứng nào nối chúng.
- **Cùng trạng thái memoization:** hai nhánh có thông tin còn lại tương đương về tương lai và giá trị, có thể gộp bằng DP/memoization dù không nhất thiết là đối xứng hình học.

Không được loại một nhánh chỉ vì nó có **giá trị hiện tại bằng** giá trị của một nhánh khác. Để gộp đúng, phải chứng minh những gì xảy ra **sau này** cũng tương đương theo mục tiêu bài toán.

## 3. Ví dụ cơ bản: hoán vị có các giá trị bằng nhau

Cho mảng giá trị:

```text
a = [1, 1, 2]
```

Nếu coi hai phần tử `1` ở hai vị trí là hai **đối tượng có nhãn**, tổng cộng có `3! = 6` hoán vị chỉ số:

```text
Dùng ký hiệu 1a, 1b, 2 để phân biệt hai chỉ số:
1a 1b 2
1a 2 1b
1b 1a 2
1b 2 1a
2 1a 1b
2 1b 1a
```

Nhưng nếu đầu ra chỉ phân biệt **giá trị** và không phân biệt `1a` với `1b`, các hoán vị trên chỉ cho **ba dãy giá trị khác nhau**:

```text
[1, 1, 2]
[1, 2, 1]
[2, 1, 1]
```

Với `a=[1,1,2,2]`:

- Nếu mỗi chỉ số được phân biệt: `4!=24` hoán vị chỉ số.
- Nếu chỉ xét dãy giá trị: `4!/(2!\cdot2!)=6` hoán vị duy nhất.

Công thức tổng quát với các nhóm giá trị có tần suất `c_1,c_2,\ldots,c_r`, tổng `n`:

\[
\text{số hoán vị giá trị duy nhất}
=\frac{n!}{c_1!\,c_2!\cdots c_r!}.
\]

Đây là số lượng **đại diện** khi ta cho phép hoán đổi tùy ý những vị trí có cùng giá trị. Mỗi hoán vị giá trị duy nhất tương ứng `c_1!c_2!\cdots c_r!` hoán vị chỉ số nếu mọi bản sao được phân biệt.

## 4. Quy tắc phá đối xứng khi sinh hoán vị duy nhất

Ta có thể **chặn nhánh thừa ngay lúc dựng lời giải**, thay vì sinh đủ `n!` lá rồi dùng `HashSet` loại các dãy trùng.

### Bước chuẩn bị

1. **Sắp xếp** bản sao mảng giá trị tăng dần.
2. Dùng `used[i]` để biết phần tử tại chỉ số `i` trong bản đã sắp có được dùng ở đường đi hiện tại không.
3. Dùng `path[depth]` ghi dãy giá trị đang dựng.
4. Ở mỗi độ sâu, thử từng chỉ số chưa dùng; sau khi đặt một giá trị, đệ quy xuống bước tiếp theo rồi **hoàn tác**.

Điều kiện bỏ qua quan trọng:

```java
if (i > 0 && values[i] == values[i - 1]
        && !used[i - 1]) {
    continue;
}
```

Nghĩa là: nếu phần tử hiện tại có **cùng giá trị với phần tử ngay trước** trong mảng đã sắp, nhưng phần tử trước **chưa được dùng** trong nhánh hiện tại, ta không cho chọn phần tử sau trước.

### Vì sao quy tắc này loại đúng phần đối xứng?

Giả sử các bản sao cùng giá trị `v` có chỉ số `p,p+1,\ldots,q` trong mảng đã sắp. Một dãy **giá trị** không thay đổi nếu hoán đổi các **bản sao `v`** cho nhau. Ta chọn quy tắc chuẩn:

> Các bản sao cùng giá trị chỉ được đưa vào `path` theo thứ tự chỉ số tăng dần.

Bất kỳ hoán vị chỉ số nào vi phạm thứ tự này đều có thể đổi tên các bản sao `v` để thành một hoán vị chỉ số **theo thứ tự chuẩn** mà không đổi **dãy giá trị**. Vậy mỗi dãy giá trị vẫn có **ít nhất một** đường đi đại diện.

Mặt khác, đối với cùng một dãy giá trị, thứ tự chọn các chỉ số trùng giá trị đã bị cố định. Không còn hai hoán vị chỉ số khác nhau tạo ra cùng dãy giá trị theo cách hoán đổi những bản sao ấy. Vậy mỗi dãy giá trị có **nhiều nhất một** đường đi đại diện.

Kết hợp hai vế: thuật toán sinh **đúng một lần** cho mỗi hoán vị giá trị khác nhau.

### Vì sao phải kiểm tra `!used[i-1]`?

Điều kiện sau là **sai**:

```java
// SAI: bỏ mọi bản sao sau bản đầu, bất kể trạng thái used.
if (i > 0 && values[i] == values[i - 1]) {
    continue;
}
```

Nó sẽ không bao giờ cho dùng bản sao `1` thứ hai của `[1,1,2]`, làm mất mọi hoán vị dài ba có hai số `1`.

Điều kiện đúng chỉ chặn việc **chọn bản sao sau trước bản sao trước**. Khi `used[i-1]==true`, ta được phép chọn bản sao hiện tại để dùng đủ số lần xuất hiện của giá trị.

### Thứ tự kiểm tra và hoàn tác

```text
sort(values)
used[*] = false

backtrack(depth):
    if depth == n:
        ghi lại một hoán vị
        return

    for i = 0..n-1:
        if used[i]: continue
        if i>0 and values[i]==values[i-1] and not used[i-1]:
            continue

        used[i] = true
        path[depth] = values[i]
        backtrack(depth+1)
        used[i] = false
```

Với `[1,1,2]`, khi đang ở độ sâu `0`, bản sao `1` thứ hai bị chặn vì bản thứ nhất chưa dùng. Khi đã chọn bản thứ nhất, bản thứ hai được dùng ở các mức tiếp theo. Nhờ đó ba dãy ở phần 3 đều xuất hiện.

**Cần phân biệt loại trùng ở một tầng của cây với loại một nhánh vì “đã từng thấy giá trị này ở đâu đó”.** Nếu dùng `HashSet` toàn cục để chặn mọi lần xuất hiện của giá trị `1`, ta sẽ không thể đặt hai số `1` vào cùng một dãy. Thông tin `used[]` hoặc tập giá trị **cục bộ theo tầng** là thiết yếu.

## 5. Hai cách loại trùng: phá đối xứng sớm và chuẩn hóa ở lá

Có hai mức xử lý thường gặp.

### 5.1. Phá đối xứng ngay khi mở rộng trạng thái

Ví dụ hoán vị dùng điều kiện `used[i-1]` trước khi đệ quy. Các nhánh bị loại **chưa được khám phá**, nên tiết kiệm cả nút nội bộ lẫn lá.

Ưu điểm:

- Thường nhanh hơn nhiều khi có các nhóm phần tử trùng lớn.
- Không cần lưu tập tất cả đầu ra chỉ để nhận diện trùng.
- Khi đã chứng minh quy tắc chuẩn, dễ kiểm soát số lượng lời giải.

Rủi ro: một điều kiện cắt quá mạnh có thể loại **mọi** cách đạt một lời giải hợp lệ. Vì vậy phải chứng minh: **mỗi lớp tương đương còn ít nhất một nhánh đại diện**.

### 5.2. Sinh lời giải rồi chuẩn hóa/khử trùng ở lá

Trong nhiều bài hình học, khó áp đặt đại diện chuẩn ngay trên trạng thái đang xây dở. Một cách an toàn về mặt ý nghĩa là:

1. Sinh một **lời giải hoàn chỉnh và hợp lệ**.
2. Tính tất cả phép biến đổi đối xứng có thể áp dụng.
3. Lấy **khóa chuẩn** của quỹ đạo (ví dụ biểu diễn nhỏ nhất theo một thứ tự cố định).
4. Đưa khóa vào `HashSet`.
5. Số khóa khác nhau bằng **số lớp lời giải theo đối xứng**.

Ví dụ:

```text
canonical(solution) =
    minLex(transform_0(solution),
           transform_1(solution),
           ...
           transform_7(solution))

uniqueCanonicalKeys.add(canonical(solution))
```

Ưu điểm: dễ mô tả và kiểm chứng trên bài như N-Queens; không cần chứng minh quy tắc cắt nhánh ở các tiền tố chưa hoàn chỉnh.

Nhược điểm: vẫn phải sinh **mọi lá hợp lệ** trước khi khử trùng, và tập khóa có thể chiếm bộ nhớ lớn. **Khử trùng ở lá giảm số kết quả giữ lại, không nhất thiết giảm số nút đã duyệt.**

### 5.3. Vì sao canonical của trạng thái dở dang cần cẩn trọng?

Một phép quay/phản chiếu có thể biến một cấu hình bàn cờ hoàn chỉnh thành một cấu hình hoàn chỉnh khác. Nhưng khi quay **một tiền tố đang đặt quân theo hàng từ trên xuống**, các quân đã đặt có thể chuyển sang những hàng **chưa được xử lý**. Phép biến đổi không nhất thiết giữ lại cùng loại tiền tố ở cùng độ sâu.

Vì vậy, không được tự áp đặt:

```text
Nếu partialBoard > mirror(partialBoard) thì bỏ ngay.
```

trừ khi đã chứng minh phép so sánh đó **tương thích với quy tắc xây từng bước** và rằng mọi quỹ đạo của những lời giải hoàn chỉnh có một tiền tố được giữ. Đôi khi có thể xây bộ phá đối xứng theo ràng buộc lexicographic toàn cục, nhưng nó cần thiết kế riêng, không phải một phép so sánh tùy ý giữa hai mảng chưa hoàn chỉnh.

## 6. N-Queens: đối xứng phản chiếu theo trục dọc

Trong bài toán **N-Queens**, cần đặt `n` quân hậu trên bàn cờ `n\times n` sao cho không có hai quân nào cùng hàng, cùng cột hoặc cùng đường chéo. Một cách quay lui phổ biến là đặt **mỗi hàng đúng một quân**, từ hàng `0` tới `n-1`.

Biểu diễn một lời giải bằng mảng:

```text
queenCol[row] = cột có quân hậu ở hàng row
```

Hai quân tại `(r_1,c_1)` và `(r_2,c_2)` xung đột nếu cùng cột hoặc:

\[
|r_1-r_2|=|c_1-c_2|.
\]

Khi đặt theo hàng tăng dần, kiểm tra ba tập đánh dấu:

- `usedColumn[c]`: cột đã có quân hậu.
- `usedDiagDown[r-c+n-1]`: đường chéo có hiệu `r-c` cố định.
- `usedDiagUp[r+c]`: đường chéo có tổng `r+c` cố định.

### Phản chiếu trục dọc

Phép phản chiếu:

\[
(r,c)\longmapsto(r,n-1-c)
\]

biến một cấu hình N-Queens hợp lệ thành một cấu hình N-Queens hợp lệ khác. Nó giữ số quân, số hàng và quan hệ không ăn nhau. Áp dụng hai lần trở về cấu hình ban đầu.

Đặc biệt, cột của **quân hậu ở hàng đầu tiên** đổi từ `c` sang `n-1-c`. Vậy ta có thể:

- Chỉ **duyệt các cột nằm ở nửa trái** của hàng đầu.
- Đếm số lời giải dưới các nhánh đó: gọi `leftCount`.
- Phản chiếu mỗi lời giải để có đối tác từ nửa phải, vì các cặp cột `c` và `n-1-c` là đối xứng.
- Nếu `n` **lẻ**, còn một cột **chính giữa** `c=n/2` tự phản chiếu vào chính cột ấy; ta phải duyệt nhánh này riêng: gọi `centerCount`.

Công thức chính xác để **đếm toàn bộ lời giải có vị trí cụ thể**:

\[
\boxed{\text{allCount}=2\cdot\text{leftCount}+\text{centerCount}}.
\]

Với `n` chẵn, không có cột giữa, `centerCount=0`.

### Bảng ví dụ số đếm

| n | Số lời giải đầy đủ | `leftCount` | `centerCount` | `2\cdot left+center` |
|---:|---:|---:|---:|---:|
| 1 | 1 | 0 | 1 | 1 |
| 4 | 2 | 1 | 0 | 2 |
| 5 | 10 | 4 | 2 | 10 |
| 8 | 92 | 46 | 0 | 92 |

Đây là **số lượng các cách đặt có tọa độ khác nhau**, không phải số lớp dưới mọi phép quay/phản chiếu.

### Lưu ý rất quan trọng khi n lẻ

Giả sử `n=5`. Hai lời giải có quân đầu tiên ở cột giữa `2` vẫn có thể là **hai cấu hình phản chiếu khác nhau**. Chỉ vì quân đầu ở giữa không có nghĩa **toàn bộ bàn cờ** bất biến qua phản chiếu.

Do đó:

- Nhánh giữa phải được **tính đầy đủ một lần** trong công thức đếm `2\cdot leftCount+centerCount`.
- Số `leftCount+centerCount` chỉ là **số lời giải dưới những nhánh hàng đầu đã duyệt**, **không nhất thiết** là số quỹ đạo phản chiếu.
- Không được tự coi “lấy nửa trái cộng nhánh giữa” là liệt kê chính xác một đại diện mỗi lớp đối xứng khi `n` lẻ, vì ngay trong nhánh giữa vẫn có thể có cặp nghiệm đối xứng.

Phân biệt **giảm cây tìm kiếm để suy ra tổng số nghiệm** với **đếm số nghiệm không tương đương theo đối xứng**. Hai mục tiêu khác nhau.

### Vì sao phép nhân 2 không làm đếm trùng nửa trái?

Với mỗi nghiệm có quân đầu ở cột `c<n/2`, nghiệm phản chiếu có quân đầu ở cột `n-1-c>n/2`, nên **không thuộc những nhánh nửa trái** đã xét. Phép phản chiếu là song ánh, vì thực hiện hai lần trở về nghiệm cũ. Do đó đếm nửa trái rồi nhân `2` là đúng cho phần không nằm giữa.

Khi `n` lẻ, các nghiệm có quân đầu ở cột giữa không đổi **cột đầu** khi phản chiếu, nên không được nhân `2`; chúng đã được tính trong `centerCount`. Đây là một ví dụ của việc phải xử lý **trạng thái cố định theo phép đối xứng** một cách cẩn thận.

## 7. Đối xứng quay và phản chiếu đầy đủ: nhóm D4 có tám phép

Bàn cờ vuông còn đối xứng theo:

- Phép quay `0^\circ` (đồng nhất).
- Phép quay `90^\circ`, `180^\circ`, `270^\circ`.
- Phản chiếu qua một trục, rồi áp dụng bốn phép quay nói trên.

Tổng cộng có **8 phép biến đổi** tạo thành nhóm đối xứng của hình vuông, thường gọi **`D_4`** (một số tài liệu ký hiệu `D_8` theo cách đặt tên nhóm có 8 phần tử). Để tránh nhầm ký hiệu, bài này dùng cụm **“8 phép đối xứng bàn cờ vuông”**.

Phép quay `90^\circ` theo chiều kim đồng hồ:

\[
(r,c)\mapsto(c,n-1-r).
\]

Phép phản chiếu trục dọc:

\[
(r,c)\mapsto(r,n-1-c).
\]

Kết hợp các phép này tạo đủ 8 phép biến đổi. Với mỗi cấu hình hoàn chỉnh `board`, ta có thể tạo ra 8 biểu diễn `board_t`, mỗi biểu diễn được mã hóa thành mảng `queenCol`. Lấy biểu diễn nhỏ nhất theo một thứ tự toàn phần **nhất quán** làm khóa chuẩn.

### Fundamental solution không bằng allCount/8 trong mọi trường hợp

Một **fundamental solution** trong N-Queens là một lớp nghiệm khi coi những cấu hình thu được bằng quay/phản chiếu là tương đương.

Một quỹ đạo có thể có **ít hơn 8 cấu hình khác nhau** nếu một số phép đối xứng giữ nguyên chính cấu hình đó. Vì vậy không thể đơn giản lấy số nghiệm đầy đủ chia `8`.

Ví dụ:

| n | Tổng nghiệm đầy đủ | Số fundamental solutions (tới 8 phép đối xứng) |
|---:|---:|---:|
| 1 | 1 | 1 |
| 4 | 2 | 1 |
| 5 | 10 | 2 |
| 8 | 92 | 12 |

Với `n=8`, `92/8=11{,}5` không phải số nguyên, trong khi số fundamental là **12**. Đây là một phản ví dụ tức thì cho quy tắc “cứ chia đều cho tám”.

Về lý thuyết nhóm, kích thước quỹ đạo bằng:

\[
|\operatorname{Orb}(x)|=\frac{|G|}{|\operatorname{Stab}(x)|},
\]

trong đó `Stab(x)` là tập các phép biến đổi giữ nguyên `x`. Với nhóm có `8` phép, kích thước quỹ đạo là một ước của `8` và phụ thuộc đối xứng nội tại của từng nghiệm.

**Quan trọng:** `n=5` có `10` nghiệm đầy đủ nhưng chỉ `2` lớp fundamental. Hai con số này hoàn toàn khác với `leftCount+centerCount=6` trong phép giảm nhánh theo cột đầu. Đây là ba đại lượng không được gọi chung là “số nghiệm duy nhất”.

## 8. Java 17+ hoàn chỉnh: hoán vị trùng, giảm nhánh N-Queens, canonical D4

Chương trình có các phần độc lập:

1. Sinh **hoán vị giá trị duy nhất** sau khi sắp mảng và dùng `used[]` + điều kiện bỏ qua giá trị trùng.
2. Đếm **hoán vị chỉ số** bằng `n!` để cho thấy số lá của phiên bản ngây thơ khi mọi vị trí được coi là có nhãn.
3. Đếm mọi lời giải N-Queens bằng quay lui hàng–cột–đường chéo.
4. Tính `leftCount`, `centerCount`, `expandedTotal` từ đối xứng phản chiếu.
5. Đếm **fundamental solutions** bằng cách chuẩn hóa từng nghiệm đầy đủ qua 8 phép đối xứng và thêm khóa vào `HashSet`.

Chương trình dùng `long` để đếm; với số `n` cực lớn cả thời gian, bộ nhớ và số đếm đều có giới hạn. Ví dụ chỉ chạy các `n` nhỏ là `1,4,5,8`. Phần N-Queens cho phép `1<=n<=14` như một giới hạn thực hành của chương trình minh họa; giới hạn đó **không** phải một định lý của bài toán.

**Tên tệp:** `SymmetryBreakingDemo.java`.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.function.Consumer;

public final class SymmetryBreakingDemo {
    private SymmetryBreakingDemo() {
    }

    // 1. Sinh hoán vị GIÁ TRỊ duy nhất, không phân biệt
    // những phần tử bằng nhau nhưng có chỉ số khác nhau.
    public static List<List<Integer>> uniquePermutations(int[] input) {
        Objects.requireNonNull(input, "input");

        int[] values = Arrays.copyOf(input, input.length);
        Arrays.sort(values);

        boolean[] used = new boolean[values.length];
        int[] path = new int[values.length];
        List<List<Integer>> answers = new ArrayList<>();

        permute(values, used, path, 0, answers);
        return answers;
    }

    private static void permute(
            int[] values, boolean[] used, int[] path,
            int depth, List<List<Integer>> answers) {
        if (depth == values.length) {
            List<Integer> result = new ArrayList<>();
            for (int value : path) {
                result.add(value);
            }
            answers.add(result);
            return;
        }

        for (int i = 0; i < values.length; i++) {
            if (used[i]) {
                continue;
            }
            if (i > 0 && values[i] == values[i - 1]
                    && !used[i - 1]) {
                continue;
            }

            used[i] = true;
            path[depth] = values[i];
            permute(values, used, path, depth + 1, answers);
            used[i] = false;
        }
    }

    // Số lá nếu phân biệt mọi vị trí: n!, với n<=20.
    public static long labeledPermutationLeaves(int n) {
        if (n < 0 || n > 20) {
            throw new IllegalArgumentException(
                "factorial must fit in long"
            );
        }
        long answer = 1L;
        for (int i = 2; i <= n; i++) {
            answer = Math.multiplyExact(answer, i);
        }
        return answer;
    }

    public record MirrorReport(
            long leftCount,
            long centerCount,
            long exploredCandidates,
            long expandedTotal) {
    }

    private static void checkBoardSize(int n) {
        if (n < 1 || n > 14) {
            throw new IllegalArgumentException(
                "this demo supports 1..14 queens"
            );
        }
    }

    // Mỗi hàng một quân. Ba mảng boolean kiểm tra cột/chéo.
    private static void searchQueens(
            int row, int n,
            boolean[] usedColumn,
            boolean[] usedDiagDown,
            boolean[] usedDiagUp,
            int[] queenCol,
            Consumer<int[]> onSolution) {
        if (row == n) {
            onSolution.accept(queenCol);
            return;
        }

        for (int col = 0; col < n; col++) {
            int down = row - col + n - 1;
            int up = row + col;
            if (usedColumn[col]
                    || usedDiagDown[down]
                    || usedDiagUp[up]) {
                continue;
            }

            usedColumn[col] = true;
            usedDiagDown[down] = true;
            usedDiagUp[up] = true;
            queenCol[row] = col;

            searchQueens(
                row + 1, n, usedColumn, usedDiagDown,
                usedDiagUp, queenCol, onSolution
            );

            usedColumn[col] = false;
            usedDiagDown[down] = false;
            usedDiagUp[up] = false;
        }
    }

    private static void visitAllQueens(
            int n, Consumer<int[]> onSolution) {
        boolean[] columns = new boolean[n];
        boolean[] down = new boolean[2 * n - 1];
        boolean[] up = new boolean[2 * n - 1];
        int[] board = new int[n];

        searchQueens(
            0, n, columns, down, up, board, onSolution
        );
    }

    // Đếm toàn bộ nghiệm, không phá đối xứng.
    public static long countAllQueens(int n) {
        checkBoardSize(n);
        long[] total = {0L};
        visitAllQueens(n, board -> total[0]++);
        return total[0];
    }

    // Chỉ xét các nghiệm có quân đầu ở một cột cố định.
    private static long countFirstColumn(int n, int firstCol) {
        boolean[] columns = new boolean[n];
        boolean[] down = new boolean[2 * n - 1];
        boolean[] up = new boolean[2 * n - 1];
        int[] board = new int[n];

        columns[firstCol] = true;
        down[n - 1 - firstCol] = true;
        up[firstCol] = true;
        board[0] = firstCol;

        long[] total = {0L};
        searchQueens(
            1, n, columns, down, up, board,
            candidate -> total[0]++
        );
        return total[0];
    }

    // Đếm bằng đối xứng phản chiếu trục dọc.
    public static MirrorReport countUsingMirror(int n) {
        checkBoardSize(n);
        long leftCount = 0L;

        for (int col = 0; col < n / 2; col++) {
            leftCount += countFirstColumn(n, col);
        }

        long centerCount = (n % 2 == 1)
            ? countFirstColumn(n, n / 2)
            : 0L;

        long explored = leftCount + centerCount;
        long total = 2L * leftCount + centerCount;
        return new MirrorReport(
            leftCount, centerCount, explored, total
        );
    }

    // Mã hóa một cấu hình hoàn chỉnh thành khóa chuẩn dưới
    // 8 phép: tùy chọn phản chiếu, sau đó quay 0/90/180/270.
    private static String canonicalD4(int[] board) {
        int n = board.length;
        String best = null;

        for (int reflection = 0; reflection < 2; reflection++) {
            for (int turns = 0; turns < 4; turns++) {
                int[] transformed = new int[n];

                for (int row = 0; row < n; row++) {
                    int r = row;
                    int c = board[row];

                    if (reflection == 1) {
                        c = n - 1 - c;
                    }
                    for (int t = 0; t < turns; t++) {
                        int newR = c;
                        int newC = n - 1 - r;
                        r = newR;
                        c = newC;
                    }
                    transformed[r] = c;
                }

                String key = Arrays.toString(transformed);
                if (best == null || key.compareTo(best) < 0) {
                    best = key;
                }
            }
        }
        return best;
    }

    // Đếm số lớp nghiệm dưới toàn bộ 8 đối xứng D4.
    // Đây là khử trùng ở lá, không phải cắt nhánh sớm.
    public static int countFundamentalQueens(int n) {
        checkBoardSize(n);
        Set<String> canonicalKeys = new HashSet<>();
        visitAllQueens(
            n, board -> canonicalKeys.add(canonicalD4(board))
        );
        return canonicalKeys.size();
    }

    public static void main(String[] args) {
        int[] first = {1, 1, 2};
        List<List<Integer>> permutations =
            uniquePermutations(first);

        System.out.println("Multiset [1,1,2]: " + permutations);
        System.out.println("Labeled leaves [1,1,2]: "
            + labeledPermutationLeaves(first.length));
        System.out.println("Unique value permutations: "
            + permutations.size());

        int[] second = {1, 1, 2, 2};
        System.out.println("Multiset [1,1,2,2] unique: "
            + uniquePermutations(second).size());
        System.out.println("Labeled leaves [1,1,2,2]: "
            + labeledPermutationLeaves(second.length));

        for (int n : new int[] {1, 4, 5, 8}) {
            long all = countAllQueens(n);
            MirrorReport mirror = countUsingMirror(n);
            int fundamental = countFundamentalQueens(n);

            if (all != mirror.expandedTotal()) {
                throw new AssertionError(
                    "Mirror formula mismatch for n=" + n
                );
            }

            System.out.println(
                "NQueens n=" + n
                + ": all=" + all
                + " mirrorCandidates="
                + mirror.exploredCandidates()
                + " expanded=" + mirror.expandedTotal()
                + " D4Fundamental=" + fundamental
            );
        }

        boolean rejected = false;
        try {
            countAllQueens(0);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("Invalid n rejected: " + rejected);
    }
}
```

Biên dịch và chạy bằng **JDK 17 hoặc mới hơn**:

```bash
javac -encoding UTF-8 SymmetryBreakingDemo.java
java SymmetryBreakingDemo
```

**Đầu ra chuẩn:**

```text
Multiset [1,1,2]: [[1, 1, 2], [1, 2, 1], [2, 1, 1]]
Labeled leaves [1,1,2]: 6
Unique value permutations: 3
Multiset [1,1,2,2] unique: 6
Labeled leaves [1,1,2,2]: 24
NQueens n=1: all=1 mirrorCandidates=1 expanded=1 D4Fundamental=1
NQueens n=4: all=2 mirrorCandidates=1 expanded=2 D4Fundamental=1
NQueens n=5: all=10 mirrorCandidates=6 expanded=10 D4Fundamental=2
NQueens n=8: all=92 mirrorCandidates=46 expanded=92 D4Fundamental=12
Invalid n rejected: true
```

### Cách đọc kết quả chương trình

- `[1,1,2]` có sáu hoán vị **chỉ số**, nhưng chỉ ba hoán vị **giá trị**; ba dãy được in theo thứ tự từ điển vì mảng được sắp trước khi quay lui.
- `[1,1,2,2]` có `24` hoán vị chỉ số và `6` hoán vị giá trị duy nhất.
- Với `n=4`, có hai nghiệm N-Queens; xét nửa trái của hàng đầu cho đúng **một** nghiệm, phản chiếu tạo nghiệm còn lại.
- Với `n=5`, có `4` nghiệm ở nhánh nửa trái và `2` nghiệm ở cột giữa, nên tổng bằng `2\cdot4+2=10`. Nhưng số `mirrorCandidates=6` **không** phải số fundamental solutions.
- Với `n=8`, có `92` nghiệm đầy đủ, `46` nghiệm dưới nhánh nửa trái và `12` lớp nghiệm dưới cả tám phép quay/phản chiếu.
- `n=1` là trường hợp có một quân ở giữa bàn cờ; việc kiểm tra nhánh giữa và các phép đối xứng phải giữ kết quả `1`, không tùy tiện nhân `2` hay `8`.
- Hàm `countFundamentalQueens` duyệt các nghiệm đầy đủ rồi chuẩn hóa; nó giảm số **khóa kết quả**, **không giảm** số lá N-Queens mà hàm phải xét.

### Giải thích mã canonical N-Queens

Mỗi nghiệm dùng mảng `board[row]=col`. Với từng phép biến đổi, chương trình tạo mảng `transformed[newRow]=newCol`, bảo toàn việc mỗi hàng có một quân. Sau đó dùng `Arrays.toString` để tạo một **khóa không mơ hồ** cho mảng chỉ số. `String.compareTo` định nghĩa một thứ tự tổng trên các khóa này; **không bắt buộc** nó đúng bằng thứ tự từ điển số học trên các mảng. Điều cần là phép so sánh **nhất quán** trên tất cả tám ảnh của mỗi quỹ đạo.

Khi một nghiệm đã được quay/phản chiếu, các phép đối xứng tiếp theo vẫn tạo ra **cùng tập tám ảnh** (tính chất nhóm). Vì vậy hai nghiệm cùng lớp đối xứng có cùng khóa nhỏ nhất và được `HashSet` gộp.

**Không giữ tham chiếu tới mảng `queenCol` đang được quay lui** làm đáp án: mảng này được tái sử dụng và thay đổi tại các bước tiếp theo. Trong mã, khóa canonical được tạo ngay ở lá thành `String` bất biến, nên không bị ảnh hưởng bởi việc hoàn tác.

## 9. Chứng minh tính đúng của hai kỹ thuật loại đối xứng

### 9.1. Với hoán vị giá trị trùng

Gọi `v` là một giá trị có nhiều bản sao ở các vị trí đã sắp `i_1<i_2<\cdots<i_t`. Hoán đổi những bản sao cùng giá trị **không thay đổi dãy giá trị** cuối cùng. Với mỗi dãy giá trị hợp lệ, luôn tồn tại cách gắn chỉ số bản sao theo thứ tự xuất hiện `i_1,i_2,\ldots,i_t`. Vì vậy quy tắc “chỉ dùng bản sao sau khi bản sao trước đã được dùng” **không làm mất** bất kỳ dãy giá trị nào.

Ngược lại, quy tắc ấy bắt buộc thứ tự dùng bản sao bằng nhau. Với cùng một dãy giá trị cuối, không tồn tại hai cách gắn chỉ số bản sao khác nhau cùng thỏa thứ tự tăng. Vì vậy mỗi dãy giá trị có **đúng một** đường đi. Điều kiện `i>0 && values[i]==values[i-1] && !used[i-1]` là chính xác.

### 9.2. Với phản chiếu N-Queens ở hàng đầu

Phản chiếu trục dọc là song ánh từ tập nghiệm có quân đầu ở cột `c` sang tập nghiệm có quân đầu ở cột `n-1-c`. Nếu `c<n/2`, cột phản chiếu nằm ở nửa phải. Hai tập không giao nhau. Vậy số nghiệm ở nửa phải **bằng** số nghiệm ở nửa trái.

Khi `n` lẻ, cột giữa phản chiếu về chính nó; các nghiệm có quân đầu ở giữa đã nằm trong `centerCount`. Chúng không được nhân hai lần. Do đó `allCount=2\cdot leftCount+centerCount`.

Chú ý phép chứng minh này chỉ xác nhận **khôi phục số nghiệm đầy đủ bằng phản chiếu trục dọc**. Nó **không** chứng minh `leftCount+centerCount` là số lớp tương đương dưới phản chiếu hoặc dưới cả tám phép đối xứng.

### 9.3. Với canonical key qua tám phép D4

Gọi `G` là tập tám phép quay/phản chiếu. Nếu `y=h(x)` với `h\in G` thì:

\[
\{g(y):g\in G\}
=\{g(h(x)):g\in G\}
=\{g(x):g\in G\}.
\]

Vì tập ảnh giống nhau, khóa nhỏ nhất cũng giống nhau. Ngược lại, nếu khóa nhỏ nhất của `x` và `y` bằng nhau, tức có một ảnh chung thuộc cả hai quỹ đạo; áp dụng phép nghịch đảo sẽ đưa từ `x` sang `y`, nên chúng thuộc cùng quỹ đạo.

Do đó `HashSet` các khóa canonical đếm đúng **số quỹ đạo**. Mỗi quỹ đạo có ít nhất một nghiệm được liệt kê bởi backtracking đầy đủ, nên không quỹ đạo nào bị bỏ.

## 10. Khi nào không được loại đối xứng?

### 10.1. Đề phân biệt nhãn và danh tính đối tượng

Nếu mảng chứa hai đồ vật cùng trọng lượng `1` nhưng có **ID A/B**, đề yêu cầu thứ tự sắp các **ID**, thì:

```text
[A, B, C] và [B, A, C]
```

là hai kết quả khác nhau dù trọng lượng lần lượt là `[1,1,2]`. Quy tắc của phần hoán vị **chỉ đúng khi đầu ra không phân biệt các bản sao bằng giá trị**.

### 10.2. Trọng số không đối xứng

Nếu bàn cờ có ô thưởng, ô cấm hoặc quân hậu có đặc tính phụ không bất biến dưới phản chiếu, cấu hình phản chiếu có thể có **điểm khác** hoặc **không hợp lệ**. Khi đó không được nhân `2` sau khi chỉ duyệt nửa trái.

Ví dụ bàn cờ N-Queens có một ô cấm ở phía trái nhưng không có ô cấm tương ứng bên phải: phép phản chiếu không còn bảo toàn tập nghiệm. **Phải kiểm tra đối xứng của toàn bộ ràng buộc, không chỉ hình dạng bảng.**

### 10.3. Đề đếm tất cả nghiệm

Nếu đề hỏi `92` cách đặt N-Queens khi `n=8`, trả `12` fundamental solutions là sai. Cần hiểu đề hỏi **toàn bộ nghiệm** hay **nghiệm đến đối xứng**.

Một cách phục hồi là khai triển từng canonical đại diện qua các phép đối xứng và loại các ảnh trùng. Không được nhân `8` cho mọi quỹ đạo nếu có những nghiệm được một phép đối xứng nào đó giữ nguyên.

### 10.4. Trạng thái có cùng dữ liệu nhìn thấy nhưng tương lai khác

Trong bài phân công, hai nhân viên có cùng năng lực hiện tại nhưng **có lịch nghỉ hoặc hạn mức khác nhau về sau** không nhất thiết hoán đổi được. Hai ô cùng màu nhưng có vị trí khác nhau trong một đồ thị bất đối xứng không phải hai trạng thái tương đương.

**Kiểm tra đúng mức:** sau phép hoán đổi, tập lựa chọn tương lai, điều kiện hợp lệ và giá trị mục tiêu đều phải tương ứng một cách một–một. Nếu không, việc xóa một nhánh có thể xóa lời giải tốt nhất.

### 10.5. Nhánh chưa hoàn chỉnh bị biến ra ngoài loại trạng thái đang duyệt

Với N-Queens đặt quân theo hàng từ trên xuống, một phép quay `90^\circ` có thể biến “đã đặt các quân ở những hàng đầu” thành “đã đặt quân trên một số cột”, không còn là tiền tố hàng. Do đó canonical của **nghiệm hoàn chỉnh** không tự động cho một điều kiện cắt **tiền tố** an toàn.

Muốn cắt sớm mạnh hơn, cần thiết kế **symmetry-breaking constraints** trên cấu trúc quyết định đầy đủ, hoặc duy trì thông tin đủ để chứng minh một đại diện của mọi quỹ đạo vẫn có nhánh đi qua.

## 11. Độ phức tạp và đánh đổi

### 11.1. Hoán vị đa tập

Với `n` phần tử, các giá trị có tần suất `c_1,\ldots,c_r` và số đầu ra duy nhất `U=n!/\prod c_i!`:

- Sắp mảng: `O(n\log n)`.
- Mỗi hoán vị duy nhất có `n` phần tử phải được tạo và lưu/in, nên riêng lượng kết quả đã là **`\Omega(U n)`**.
- Backtracking ở mỗi nút có thể quét tới `n` chỉ số; một chặn trên dễ dùng cho cài đặt trực tiếp là **`O(n^2 U+n\log n)`** trong trường hợp tổng quát, do số tiền tố hợp lệ không vượt một bội số theo `n` của số lá và mỗi nút quét `n` lựa chọn. Cận này không nhất thiết chặt.
- Bộ nhớ làm việc (không tính danh sách kết quả): `O(n)` cho `used`, `path` và độ sâu đệ quy.
- Bộ nhớ chứa toàn bộ kết quả: **`O(nU)`**. Nếu chỉ đếm hoặc xuất lần lượt, có thể tránh giữ toàn bộ các hoán vị trong RAM.

So với sinh `n!` hoán vị chỉ số rồi loại trùng ở lá, phá đối xứng sớm giúp giảm mạnh cây tìm kiếm khi có nhiều giá trị lặp. Nếu tất cả giá trị khác nhau, không có đối xứng theo bản sao bằng nhau để loại, số hoán vị vẫn là `n!`.

### 11.2. N-Queens

Quay lui N-Queens vẫn có thể rất lớn khi `n` tăng. Phép phản chiếu hàng đầu chỉ giảm một phần số nhánh tìm kiếm, **không** biến bài toán thành đa thức.

Với `n` chẵn, ta duyệt một nửa lựa chọn ở hàng đầu và nhân số nghiệm `2`. Với `n` lẻ, còn nhánh giữa. Mức tiết kiệm thực tế phụ thuộc số cây con và chi phí mỗi cây con; không được khẳng định thời gian luôn chia chính xác `2`.

- Bộ nhớ mảng cột/chéo/board và ngăn xếp đệ quy: **`O(n)`**.
- Đếm `countAllQueens` và `countUsingMirror` không cần giữ các nghiệm.
- `countFundamentalQueens` dùng `HashSet` chứa một khóa cho mỗi quỹ đạo, nên cần thêm bộ nhớ tỷ lệ với số quỹ đạo nhân kích thước khóa `O(n)`. Mỗi nghiệm lá được chuẩn hóa qua tám phép, mỗi phép duyệt `n` quân, nên riêng chi phí chuẩn hóa là **`O(8n)` trên mỗi nghiệm**; số nghiệm vẫn có thể rất lớn.

Nếu bài thực sự yêu cầu **chỉ một đại diện mỗi quỹ đạo** và số nghiệm lớn, cần các quy tắc phá đối xứng tinh vi hơn để giảm cả cây tìm kiếm. Tuy vậy phải chứng minh điều kiện canonical có thể áp dụng **trong lúc xây trạng thái**, không suy từ việc canonical đúng ở lá.

## 12. Kiểm thử và đối chứng độc lập

Vì cắt nhánh có nguy cơ bỏ nhầm lời giải, kiểm thử nên so một bản **không dùng phá đối xứng** với bản có loại trùng hoặc đếm bù.

### 12.1. Kiểm tra hoán vị

Với mảng ngắn:

1. Sinh tất cả `n!` hoán vị **chỉ số**.
2. Chuyển chúng thành dãy **giá trị**, đưa vào `HashSet`.
3. Sinh bằng thuật toán `used[i-1]`.
4. So **tập dãy giá trị**, không chỉ so số lượng.
5. Kiểm tra không có hai kết quả lặp và mỗi kết quả dùng đúng số lần của từng giá trị đầu vào.

Ca bắt buộc:

```text
[]            -> 1 hoán vị rỗng: []
[1]           -> 1
[1,1]         -> 1: [1,1]
[1,1,2]       -> 3
[1,1,2,2]     -> 6
[1,2,3]       -> 6
[2,1,1]       -> đúng ba hoán vị như [1,1,2]
```

**Lưu ý:** với mảng rỗng, kết quả là **một hoán vị rỗng** `[[]]` theo quy ước toán học: có đúng một cách sắp xếp không phần tử. Đừng nhầm `[[]]` với một danh sách kết quả hoàn toàn rỗng `[]`.

### 12.2. Kiểm tra N-Queens

- Tạo mọi nghiệm từ backtracking đầy đủ.
- Đối chiếu tổng số với công thức phản chiếu `2\cdot leftCount+centerCount`.
- Với từng nghiệm, phản chiếu/quay rồi kiểm tra **vẫn là cấu hình hợp lệ**.
- Tính canonical key, xác nhận **mọi ảnh của cùng một nghiệm** đều có cùng khóa.
- Đếm số khóa khác nhau cho `n=1,4,5,8`, đối chiếu `1,1,2,12`.
- Kiểm tra những nghiệm có quân đầu ở cột giữa khi `n` lẻ; không nhân đôi nhánh giữa.
- Thử một bài biến thể có ô cấm **bất đối xứng** để thấy phép phản chiếu không còn là đối xứng của toàn bộ bài toán.

### 12.3. Sinh phản ví dụ cho quy tắc cắt sai

Đừng chỉ sinh dữ liệu ngẫu nhiên rồi mong tình cờ tìm được lỗi. Chủ động thiết kế:

- Hai bản sao cùng giá trị cần xuất hiện **cùng trong một hoán vị**.
- Hai quân đầu ở cột giữa với `n` lẻ nhưng phần còn lại là hai ảnh phản chiếu khác nhau.
- Một trường hợp số nghiệm theo D4 **không chia hết cho `8`**.
- Các đối tượng có cùng giá trị nhưng **khác nhãn**, khiến việc gộp là sai.
- Các ràng buộc phụ phá đối xứng trái/phải.

Một **phản ví dụ nhỏ** đủ bác bỏ một quy tắc loại nhánh không đúng, trong khi rất nhiều ca PASS chỉ cho thấy chưa tìm thấy lỗi.

## 13. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Coi hai trạng thái có cùng điểm là đối xứng | Bỏ những đường đi khác nhau với tương lai khác nhau | Chứng minh tồn tại phép biến đổi bảo toàn cả bài toán |
| Dùng điều kiện trùng giá trị khi đối tượng có ID khác | Mất kết quả có nhãn mà đề yêu cầu | Xác định rõ đầu ra phân biệt chỉ số hay giá trị |
| Hoán vị: bỏ mọi `values[i]==values[i-1]` | Không thể chọn đủ các bản sao trùng nhau | Dùng thêm `!used[i-1]` |
| Không sắp mảng trước khi xét cặp kề bằng nhau | Bỏ trùng không đầy đủ hoặc sai | Sắp bản sao trước khi quay lui |
| Dùng `HashSet` giá trị toàn cục ở mọi độ sâu | Không thể dùng một giá trị lặp nhiều lần trong một hoán vị | Dùng `used[]` theo chỉ số hoặc tập cục bộ mỗi tầng |
| Quên hoàn tác `used[i]=false` | Cây tìm kiếm mất các nhánh hợp lệ | Luôn hoàn tác đúng sau đệ quy |
| Đếm `n!` là số hoán vị giá trị khi có trùng | Đếm thừa | Dùng `n!/\prod c_i!` |
| Nhân đôi cả nhánh giữa khi N-Queens có `n` lẻ | Đếm thừa nghiệm | Dùng `2\cdot leftCount+centerCount` |
| Coi `leftCount+centerCount` là số quỹ đạo phản chiếu khi `n` lẻ | Nhánh giữa có thể vẫn chứa các cặp nghiệm phản chiếu | Phân biệt ứng viên đã duyệt với lớp đối xứng |
| Lấy `allCount/8` để đếm fundamental | Sai khi một nghiệm có đối xứng nội tại | Canonical hóa hoặc tính kích thước từng quỹ đạo |
| Chỉ so canonical tại lá nhưng tuyên bố đã giảm nút tìm kiếm | Không thực sự cắt các nhánh trước lá | Phân biệt giảm **đầu ra** với giảm **cây** |
| Cắt tiền tố theo đối xứng không bảo toàn thứ tự xây | Có thể xóa mọi đại diện của một quỹ đạo | Chứng minh quy tắc phá đối xứng cho trạng thái dở dang |
| Phản chiếu bàn cờ có ô cấm/điểm số lệch | Không bảo toàn tính hợp lệ hoặc điểm | Kiểm tra toàn bộ dữ liệu đầu vào có đối xứng |
| Lưu tham chiếu trực tiếp tới mảng `board` đang backtrack | Kết quả cũ bị thay đổi khi tiếp tục duyệt | Sao chép trạng thái hoặc tạo khóa bất biến ở lá |
| Không phân biệt nhãn của nghiệm khi đưa vào `HashSet` | Gộp nhầm các lời giải khác nhau | Định nghĩa rõ khóa tương đương |
| Dùng cùng tên “unique” cho nhiều loại đếm | Nhầm toàn bộ nghiệm, nhánh nửa trái, quỹ đạo phản chiếu và quỹ đạo D4 | Đặt tên biến và báo cáo rõ đại lượng |

## 14. Bài tập tự luyện

**Bài 1 — Hoán vị giá trị.** Với `[1,1,2]`, hãy liệt kê các hoán vị giá trị khác nhau. Vì sao không có sáu kết quả?

*Đáp án:* `[1,1,2]`, `[1,2,1]`, `[2,1,1]`. Hai số `1` không phân biệt trong đầu ra, nên hoán đổi hai bản sao không sinh dãy giá trị mới.

**Bài 2 — Ý nghĩa `used[]`.** Trong mảng đã sắp `[1,1,2]`, tại sao khi `used[0]=true` lại được phép chọn chỉ số `1`, còn khi `used[0]=false` thì chưa nên chọn chỉ số `1`?

*Đáp án:* thứ tự chuẩn của các bản sao `1` là chỉ số `0` trước `1`. Chỉ cấm **dùng bản sau trước bản trước**, không cấm dùng cả hai.

**Bài 3 — Tính số hoán vị đa tập.** Mảng `[1,1,1,2,2]` có bao nhiêu hoán vị giá trị duy nhất?

*Đáp án:* `5!/(3!\cdot2!)=10`.

**Bài 4 — Gắn nhãn.** Có hai quyển sách khác nhau A, B cùng màu đỏ và một quyển C màu xanh. Nếu đề hỏi thứ tự **ba quyển sách theo ID**, có được gộp `[A,B,C]` với `[B,A,C]` không?

*Đáp án:* không. Hai quyển là hai đối tượng có nhãn khác nhau; chỉ màu sắc giống nhau không làm chúng thành cùng một kết quả.

**Bài 5 — Phản chiếu N-Queens.** Với `n=8`, nếu các nhánh đặt quân đầu trong cột `0..3` cho `46` nghiệm, tổng số nghiệm đầy đủ là bao nhiêu?

*Đáp án:* `92`, do ảnh phản chiếu có quân đầu ở các cột `7..4`, không trùng nửa trái.

**Bài 6 — N lẻ.** Với `n=5`, `leftCount=4` và `centerCount=2`, tính tổng số nghiệm. Vì sao không phải `2(4+2)`?

*Đáp án:* `2\cdot4+2=10`. Hai nghiệm ở cột giữa đã được xét đầy đủ, không được nhân đôi nhánh này.

**Bài 7 — Đối xứng đầy đủ.** Với `n=8` có `92` nghiệm N-Queens, vì sao không được nói có đúng `92/8` fundamental solutions?

*Đáp án:* các quỹ đạo có thể nhỏ hơn `8` nếu cấu hình có đối xứng nội tại; hơn nữa `92/8` không nguyên. Số fundamental thực tế là `12`.

**Bài 8 — Mảng rỗng.** `uniquePermutations(new int[0])` nên trả bao nhiêu hoán vị theo quy ước toán học?

*Đáp án:* một hoán vị rỗng, tức danh sách kết quả `[[]]`, không phải danh sách không có kết quả.

**Bài 9 — Bài có vật cản.** Nếu N-Queens thêm một ô cấm ở `(0,0)` nhưng không cấm ô đối xứng `(0,n-1)`, có thể cứ giữ nhánh nửa trái và nhân đôi không?

*Đáp án:* không thể khẳng định. Phản chiếu không còn là đối xứng của **toàn bộ bài toán có vật cản**, nên phải kiểm tra lại ràng buộc hoặc bỏ tối ưu phản chiếu.

**Bài 10 — Kết quả ở lá và cắt sớm.** Vì sao dùng `HashSet` các khóa canonical tại **lá** không đồng nghĩa với việc giảm số lần gọi backtracking?

*Đáp án:* tất cả nhánh và nghiệm vẫn được sinh trước khi chuẩn hóa; chỉ số lượng kết quả giữ lại giảm. Muốn giảm cả cây phải chặn nhánh ngay khi có đủ cơ sở chứng minh an toàn.

**Bài 11 — Tự kiểm thử.** Viết bộ sinh hoán vị chỉ số cho `n<=8` và đối chứng tập dãy giá trị với thuật toán bỏ trùng. Viết thêm kiểm thử N-Queens: với mỗi nghiệm, áp dụng 8 phép biến đổi, kiểm tra tính hợp lệ và canonical key không đổi.

*Gợi ý:* kiểm tra **tập kết quả**, không chỉ số lượng, và lưu các phản ví dụ ngắn làm regression test.

## Ghi nhớ

**Loại bỏ trạng thái đối xứng giúp quay lui tránh xét hoặc lưu nhiều biểu diễn của cùng một nghiệm**, nhưng chỉ đúng sau khi ta định nghĩa **phép biến đổi bảo toàn bài toán** và hiểu rõ đề yêu cầu **đếm/liệt kê nghiệm đầy đủ hay nghiệm tới đối xứng**.

Với **hoán vị có giá trị trùng**, sắp mảng và chỉ chọn bản sao sau khi bản sao trước đã được dùng; điều kiện `values[i]==values[i-1] && !used[i-1]` giữ đúng **một đường đi cho mỗi dãy giá trị**. Với **N-Queens**, có thể giảm nhánh hàng đầu theo phản chiếu, dùng công thức `allCount=2\cdot leftCount+centerCount`; riêng `centerCount` không nhân đôi khi `n` lẻ. Để đếm **fundamental solutions dưới 8 phép quay/phản chiếu**, dùng khóa canonical của mỗi quỹ đạo, không chia tổng nghiệm cho `8` một cách máy móc.

Khi không chắc, hãy viết bản **quay lui đầy đủ** làm baseline, phát biểu chính xác tính đối xứng, thử phản ví dụ và đối chứng tập nghiệm trước khi cắt nhánh. **Một phép cắt nhanh nhưng làm mất lời giải không phải tối ưu hóa đúng.**

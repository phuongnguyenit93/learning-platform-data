# Tìm kiếm trên ma trận có cấu trúc thứ tự

Tìm kiếm một giá trị trong ma trận có thể đơn giản là kiểm tra từng ô, nhưng **nếu ma trận có quy luật thứ tự đã được bảo đảm**, ta có thể loại bỏ nhiều ô mà không cần đọc chúng. Điều khó nhất không phải viết vòng lặp, mà là hiểu chính xác **ma trận được sắp xếp theo cách nào**. Ba phát biểu “mỗi hàng đã sắp xếp”, “mỗi hàng và mỗi cột đều đã sắp xếp” và “toàn bộ ma trận đã sắp xếp theo thứ tự hàng” **không tương đương**; dùng thuật toán dành cho cấu trúc mạnh hơn khi đề bài chỉ bảo đảm cấu trúc yếu hơn sẽ dẫn đến kết quả sai.

Bài học trình bày các chiến lược tìm kiếm phù hợp với mỗi dạng thứ tự, bất biến chứng minh tính đúng, độ phức tạp theo số hàng và số cột, các trường hợp biên, phần tử trùng nhau và ví dụ Java 17+ chạy độc lập.

**Mục tiêu học tập:** nhận diện đúng cấu trúc thứ tự qua đặc tả và phản ví dụ; chọn duyệt toàn bộ, tìm kiếm nhị phân từng hàng, tìm kiếm từ góc hoặc tìm kiếm nhị phân trên chỉ số ảo; hiểu khi nào kết quả chỉ là “một vị trí bất kỳ” và khi nào có thể tìm vị trí đầu tiên; không dùng tìm kiếm nhị phân dạng làm phẳng cho ma trận chỉ có từng hàng/từng cột tăng dần.

## 1. Bài toán, chỉ số và hợp đồng đầu vào

Cho ma trận chữ nhật có `m` hàng và `n` cột, mỗi ô chứa một số nguyên `a[r][c]`, với chỉ số **0-based**:

- `0 ≤ r < m` là chỉ số hàng.
- `0 ≤ c < n` là chỉ số cột.
- Mục tiêu cơ bản là xác định liệu `target` có xuất hiện trong ma trận không; nếu có, trả lại **một cặp tọa độ hợp lệ** `(r,c)`, nếu không có thì trả `(-1,-1)`.
- Nếu cần **tọa độ đầu tiên theo thứ tự hàng** (row-major), nghĩa là chọn cặp có `r` nhỏ nhất, rồi trong hàng đó chọn `c` nhỏ nhất. Đây là mục tiêu khác với “một vị trí bất kỳ”, đặc biệt khi phần tử trùng nhau.

Ma trận **chữ nhật** có nghĩa tất cả hàng đều tồn tại, không phải `null`, và cùng số cột. Mảng hai chiều Java `int[][]` có thể là **jagged array** (các hàng dài khác nhau), nên các thuật toán sử dụng `n = a[0].length` và giả định mọi hàng cùng dài đòi hỏi tiền điều kiện chữ nhật. Một ma trận rỗng theo nghĩa có 0 hàng hoặc 0 cột không chứa phần tử nào.

Nếu không có bất kỳ bảo đảm thứ tự nào, cách đúng là kiểm tra tất cả ô từ trên xuống dưới, trái sang phải rồi dừng khi tìm thấy. Trường hợp xấu cần kiểm tra `m·n` ô, tức **Θ(mn)** thời gian, O(1) bộ nhớ phụ; chỉ tìm thấy sớm khi phần tử may mắn nằm gần đầu.

**Chọn thuật toán bằng cách đọc tiền điều kiện:** không được tự giả định ma trận đã sắp xếp vì các hàng trông có vẻ tăng ở vài ví dụ. Tính đúng đắn phải dựa trên **mọi đầu vào được đề bài cho phép**.

## 2. Ba dạng ma trận có cấu trúc thứ tự

### 2.1. Chỉ từng hàng được sắp xếp

Với mọi hàng r và mọi cột kề nhau:

`a[r][c] ≤ a[r][c+1]`.

Không có giả thiết về thứ tự giữa hai hàng hay giữa hai ô cùng cột khác hàng. Ví dụ:

~~~text
 1   4   9  13
 2   3   8  11
-5   0   7  20
~~~

Mỗi hàng đều không giảm. Nhưng cột đầu là `1,2,-5`, không tăng, và nếu đọc hết hàng đầu rồi qua hàng thứ hai, dãy `1,4,9,13,2,3,...` cũng không tăng.

**Chiến lược hợp lệ:** tìm kiếm nhị phân riêng trên từng hàng, hoặc quét từng hàng. Với `m` hàng, mỗi hàng có `n` phần tử, tìm kiếm nhị phân từng hàng cho thời gian xấu nhất **O(m log(n+1))**, bộ nhớ phụ O(1) nếu viết vòng lặp. Có thể bỏ qua một hàng khi `target < a[r][0]` hoặc `target > a[r][n-1]`, vì toàn bộ giá trị hàng đó nằm giữa hai biên; việc loại trừ **chỉ áp dụng cho chính hàng ấy**.

### 2.2. Từng hàng và từng cột đều được sắp xếp không giảm

Ngoài hàng tăng, còn có điều kiện:

`a[r][c] ≤ a[r+1][c]` cho mọi chỉ số có nghĩa.

Ví dụ ma trận 5×5:

~~~text
 1   4   7  11  15
 2   5   8  12  19
 3   6   9  16  22
10  13  14  17  24
18  21  23  26  30
~~~

Mỗi hàng tăng từ trái sang phải, mỗi cột tăng từ trên xuống dưới. Nhưng **toàn bộ dãy theo thứ tự hàng không tăng**: giá trị cuối hàng đầu `15` lớn hơn giá trị đầu hàng hai `2`.

**Chiến lược đặc trưng:** bắt đầu ở **góc trên bên phải** và mỗi bước loại bỏ một hàng hoặc một cột, gọi là *staircase search* (tìm kiếm bậc thang). Trường hợp xấu **O(m+n)** thời gian, O(1) bộ nhớ phụ. Ma trận không cần có các giá trị phân biệt; ký hiệu `≤` đã cho phép trùng nhau.

### 2.3. Toàn bộ phần tử tăng theo thứ tự hàng (row-major sorted)

Ma trận thỏa cả hai điều kiện:

1. Mỗi hàng được sắp xếp không giảm.
2. Với hai hàng liên tiếp: `a[r][n−1] ≤ a[r+1][0]`.

Ví dụ:

~~~text
 1   3   5   7
10  11  16  20
23  30  34  60
~~~

Nếu đọc từ trái sang phải, hết hàng này đến hàng khác, ta có:

`[1,3,5,7,10,11,16,20,23,30,34,60]`,

là một dãy không giảm. Vì vậy có thể tưởng tượng ma trận như **một mảng ảo đã sắp xếp gồm `m·n` phần tử**, rồi tìm kiếm nhị phân mà không cần sao chép dữ liệu. Thời gian **O(log(mn))**, bộ nhớ phụ O(1) theo mô hình RAM.

Từ tính chất này suy ra từng hàng và từng cột cũng không giảm, nhưng chiều ngược lại **không đúng**.

### 2.4. Bảng quyết định nhanh

| Bảo đảm được nêu trong đề | Thuật toán hợp lệ | Thời gian tìm một giá trị, trường hợp xấu |
|---|---|---|
| Không có thứ tự | Quét tất cả ô | O(mn) |
| Chỉ mỗi hàng không giảm | Tìm nhị phân trên từng hàng | O(m log(n+1)) |
| Cả hàng và cột đều không giảm | Tìm từ góc trên-phải hoặc dưới-trái | O(m+n) |
| Mỗi hàng không giảm **và** cuối hàng trước không lớn hơn đầu hàng sau | Tìm nhị phân trên chỉ số row-major ảo | O(log(mn)) |

Các cận trên xét phép so sánh và truy cập `int` có chi phí O(1). Với `m,n>0`, tìm kiếm nhị phân có chi phí O(log(mn)); để biểu diễn cả trường hợp chỉ một phần tử, có thể viết O(log(mn+1)). Không nên cộng phí xác minh dữ liệu đã sắp xếp vào thuật toán nếu **đề bài cho sẵn** bất biến thứ tự. Nếu phải tự sắp xếp hoặc kiểm tra từng ô, chi phí tiền xử lý cần được cộng riêng.

## 3. Tìm kiếm nhị phân trên từng hàng

Giả sử chỉ biết mỗi hàng đã sắp xếp. Ta cần tránh thuật toán nhị phân “toàn ma trận” vì thứ tự giữa các hàng không được đảm bảo.

Với mỗi hàng `r = 0..m−1`:

1. Nếu hàng rỗng, bỏ qua; trong ma trận chữ nhật có `n=0` thì tất cả hàng đều rỗng.
2. Nếu `target` nhỏ hơn phần tử đầu hoặc lớn hơn phần tử cuối, toàn bộ hàng không thể chứa `target` nên bỏ qua.
3. Tìm kiếm nhị phân trong đoạn chỉ số của hàng để tìm vị trí đầu tiên có giá trị `≥ target` (*lower bound*).
4. Nếu vị trí tìm được nằm trong hàng và có giá trị bằng `target`, trả tọa độ; nếu không, chuyển sang hàng kế tiếp.

Thuật toán lower bound 0-based cho một hàng:

~~~java
// Minh họa phương thức, cần đặt trong lớp Java để chạy độc lập.
static int lowerBound(int[] row, int target) {
    int low = 0;
    int high = row.length; // [low, high)
    while (low < high) {
        int mid = low + (high - low) / 2;
        if (row[mid] < target) {
            low = mid + 1;
        } else {
            high = mid;
        }
    }
    return low; // Chỉ số đầu tiên >= target; có thể bằng row.length.
}
~~~

**Bất biến:** tại mỗi bước, mọi vị trí nhỏ hơn `low` đều có giá trị nhỏ hơn target, và mọi vị trí từ `high` trở đi (nếu có) đều lớn hơn hoặc bằng target. Sau khi `low==high`, đó chính là vị trí đầu tiên không nhỏ hơn target. Kiểm tra thêm `row[low]==target` là bắt buộc: lower bound có thể trỏ tới giá trị **lớn hơn** target hoặc tới vị trí `row.length`.

Quét các hàng theo thứ tự tăng dần và dùng lower bound trả **tọa độ xuất hiện đầu tiên theo row-major**, ngay cả khi chỉ có từng hàng được sắp xếp. Vì vậy thuật toán cũng xử lý phần tử trùng nhau một cách rõ ràng.

**Chi phí:** giả sử có m hàng, mỗi hàng có n phần tử và n≥1. Mỗi hàng cần O(1) thao tác kiểm tra biên và O(log(n+1)) cho lower bound; tổng O(m log(n+1)) thời gian, O(1) bộ nhớ phụ. Nếu n=0, chỉ cần xét cấu trúc rỗng. Nếu chiều dài từng hàng thay đổi, có thể dùng cách tìm trên từng hàng độc lập, nhưng phải định nghĩa lại hợp đồng chỉ số và chi phí theo từng chiều dài; các thuật toán ở các phần sau yêu cầu ma trận chữ nhật.

**Ví dụ:** với ma trận chỉ sắp xếp theo hàng ở `2.1` và target `7`: hai hàng đầu không chứa 7; hàng thứ ba `[-5,0,7,20]` có 7 ở cột 2, nên trả `(2,2)`. Target `11` xuất hiện ở `(1,3)`.

## 4. Tìm kiếm bậc thang trên ma trận có hàng và cột không giảm

Đây là thuật toán quan trọng nhất khi đề bài bảo đảm **cả hai chiều** được sắp xếp nhưng **không bảo đảm row-major toàn cục**.

### 4.1. Bắt đầu từ góc trên bên phải

Đặt:

`r=0, c=n−1`.

Khi vị trí `(r,c)` còn nằm trong ma trận:

- Nếu `a[r][c] == target`: tìm thấy, trả `(r,c)`.
- Nếu `a[r][c] > target`: do cột c không giảm từ trên xuống, **mọi ô bên dưới trong cột c** đều ≥ `a[r][c]` > target. Toàn bộ **cột c của vùng đang xét** có thể bị loại, nên giảm `c` một đơn vị.
- Nếu `a[r][c] < target`: do hàng r không giảm từ trái sang phải, **mọi ô bên trái trong hàng r** đều ≤ `a[r][c]` < target. Toàn bộ **hàng r của vùng đang xét** có thể bị loại, nên tăng `r` một đơn vị.

Mã ý tưởng:

~~~java
// Mã minh họa; điều kiện tiên quyết:
// a là ma trận chữ nhật, cả hàng và cột đều không giảm.
int r = 0;
int c = columns - 1;
while (r < rows && c >= 0) {
    int value = a[r][c];
    if (value == target) {
        return new Cell(r, c);
    }
    if (value > target) {
        c--;
    } else {
        r++;
    }
}
return new Cell(-1, -1);
~~~

Đoạn trên cần được đặt vào một phương thức Java với `rows`, `columns`, `a`, `target` và kiểu `Cell` được khai báo; chương trình chạy hoàn chỉnh ở `7`.

### 4.2. Minh họa đường đi

Dùng ma trận 5×5 ở `2.2` và `target=5`:

1. `(0,4)=15 > 5` ⇒ bỏ cột 4 trong vùng đang xét, đi sang trái.
2. `(0,3)=11 > 5` ⇒ bỏ cột 3, đi sang trái.
3. `(0,2)=7 > 5` ⇒ bỏ cột 2, đi sang trái.
4. `(0,1)=4 < 5` ⇒ bỏ hàng 0 trong vùng đang xét, đi xuống.
5. `(1,1)=5` ⇒ tìm thấy.

Đường đi là `(0,4)→(0,3)→(0,2)→(0,1)→(1,1)`. Ta chỉ kiểm tra **5 ô**, thay vì tối đa 25 ô của cách quét toàn bộ.

Với `target=20`, ma trận không chứa 20. Đường đi lần lượt đọc `15,19,22,16,17,26,23,21,18`, rồi đi ra ngoài đáy ma trận và trả “không tìm thấy”. Mọi ô chưa xét đã bị loại theo bất biến thứ tự.

### 4.3. Chứng minh đúng bằng vùng ứng viên

Ban đầu vùng có khả năng chứa target là toàn bộ ma trận. Trong quá trình chạy, duy trì bất biến:

**Nếu target còn tồn tại trong các ô chưa loại, thì nó nằm trong hình chữ nhật gồm các hàng `r..m−1` và các cột `0..c`.**

- **Cơ sở:** tại `r=0, c=n−1`, vùng ứng viên chính là toàn bộ ma trận.
- **Nếu `value > target`:** các phần tử ở cột c và hàng từ r trở xuống đều ≥ value; không phần tử nào ở đó bằng target. Loại cột c bằng `c--` vẫn giữ mọi đáp án có thể có trong vùng còn lại.
- **Nếu `value < target`:** các phần tử ở hàng r và cột 0..c đều ≤ value; không phần tử nào ở đó bằng target. Loại hàng r bằng `r++` vẫn giữ mọi đáp án có thể có trong vùng còn lại.
- **Nếu bằng nhau:** tọa độ hiện tại là một đáp án đúng.
- **Nếu `r==m` hoặc `c<0`:** hình chữ nhật ứng viên rỗng. Theo bất biến, target không xuất hiện ở nơi nào có thể còn phù hợp; trả không tìm thấy là đúng.

Lập luận dùng cả **thứ tự trong hàng** và **thứ tự trong cột**, không dựa trên hình dáng hoặc vị trí “có vẻ gần” của target.

### 4.4. Vì sao O(m+n), không phải O(mn)?

Mỗi lần so sánh không thành công, thuật toán làm đúng **một** trong hai việc: tăng r hoặc giảm c. Giá trị r chỉ tăng từ 0 tới m; c chỉ giảm từ n−1 tới -1. Vì không có bước đi ngược, thuật toán thăm nhiều nhất `m+n−1` ô khi `m,n≥1`, nên thời gian O(m+n), bộ nhớ phụ O(1).

Có ma trận và target khiến đường đi dài tỉ lệ với m+n; do đó cận xấu nhất Θ(m+n) là chặt cho chiến lược này. Nhưng một truy vấn cụ thể có thể kết thúc ngay ô đầu tiên, nên không phải mọi lần gọi đều tốn m+n bước.

**Phương án đối xứng:** bắt đầu ở góc **dưới bên trái** `(m−1,0)`. Nếu `value > target` thì đi **lên** vì các ô bên phải trong hàng hiện tại đều ≥ value; nếu `value < target` thì đi **sang phải** vì các ô phía trên trong cột hiện tại đều ≤ value. Góc trên-trái và dưới-phải không cho hai hướng loại trừ tương tự bằng quy tắc đơn giản này; lựa chọn góc là một phần của chứng minh.

## 5. Tìm kiếm nhị phân trên ma trận row-major toàn cục

Nếu **toàn bộ** ma trận được sắp xếp theo thứ tự hàng (không chỉ mỗi hàng và mỗi cột), ta có thể ánh xạ một chỉ số tuyến tính `k` tới tọa độ:

- `r = k / n`, lấy phần nguyên.
- `c = k % n`, lấy phần dư.
- `0 ≤ k < m·n`.

Khi đó giá trị thứ k trong dãy ảo là `a[k/n][k%n]`. Không cần tạo mảng một chiều mới, nên vẫn dùng O(1) bộ nhớ phụ.

Ví dụ ma trận 3×4 ở `2.3` có `m·n=12`. Chỉ số `k=6` tương ứng `r=6/4=1`, `c=6%4=2`, chứa `a[1][2]=16`.

### 5.1. Dùng lower bound để xử lý phần tử trùng nhau

Đặt khoảng tìm kiếm nửa mở `[low,high)=[0,mn)`. Trong mỗi vòng:

1. `mid=low+(high−low)/2`.
2. Đọc `value=a[mid/n][mid%n]`.
3. Nếu `value < target` thì mọi phần tử ở trước hoặc tại mid đều nhỏ hơn target; đặt `low=mid+1`.
4. Ngược lại đặt `high=mid`, vì vị trí đầu tiên có giá trị ≥ target có thể là mid hoặc nằm bên trái.

Khi `low==high`, low là chỉ số đầu tiên có giá trị **≥ target** nếu tồn tại. Chỉ trả tọa độ khi `low<mn` và giá trị tại low thực sự **bằng target**; nếu không thì trả `(-1,-1)`.

Kỹ thuật này không chỉ tìm “một ô bất kỳ” mà tìm đúng **ô đầu tiên theo row-major** khi nhiều ô có giá trị target. Ví dụ:

~~~text
1  2  2
2  2  4
~~~

Với target 2, lower bound trên dãy ảo `[1,2,2,2,2,4]` trả `k=1` tương ứng `(0,1)`. Ngược lại, tìm bậc thang từ góc trên bên phải có thể gặp `(0,2)` trước: cả hai đều là đáp án hợp lệ nếu đề chỉ yêu cầu **một vị trí**, nhưng không tương đương nếu cần **vị trí đầu tiên**.

### 5.2. Bất biến và tính đúng

Đối với dãy ảo **đã sắp xếp không giảm**, invariant lower bound là:

- Mọi chỉ số `k < low` có giá trị nhỏ hơn target.
- Mọi chỉ số `k ≥ high` có giá trị lớn hơn hoặc bằng target.

Khởi tạo `low=0, high=mn` thỏa bất biến rỗng ở hai phía. Quy tắc cập nhật `low` hoặc `high` bảo toàn bất biến nhờ **tính tăng của toàn bộ dãy ảo**, không chỉ của từng hàng. Khi hai biên gặp nhau, đó là vị trí chuyển từ nhỏ hơn target sang lớn hơn hoặc bằng target. Kiểm tra bằng nhau giúp quyết định có tồn tại target hay không.

**Vì sao cần điều kiện giữa hai hàng?** Với ma trận chỉ có hàng và cột không giảm:

~~~text
1  4  7
2  5  8
3  6  9
~~~

Dãy theo row-major là `[1,4,7,2,5,8,3,6,9]`, không tăng vì có bước `7→2` và `8→3`. Binary search toàn cục không còn bất biến; có thể bỏ qua giá trị có thật và báo sai. Ma trận này **hợp lệ cho staircase search**, nhưng **không hợp lệ cho binary search trên chỉ số ảo**.

### 5.3. Tràn số khi tính chỉ số ảo

Tránh tính `int total = rows * cols` nếu tích có thể vượt miền `int`. Trong Java, phép nhân hai `int` được thực hiện trong `int` trước khi gán kết quả, kể cả khi biến đích là `long`:

~~~java
long unsafe = rows * cols;      // Có thể tràn int trước khi gán.
long safe = (long) rows * cols; // Ép kiểu trước phép nhân.
~~~

Dùng `long low, high, mid` và tính `mid = low + (high-low)/2` để tránh cộng hai chỉ số lớn trực tiếp. Khi `mid < (long)rows*cols` và `cols>0`, phép chia/lấy dư khôi phục hàng/cột hợp lệ; có thể ép hai kết quả về `int` để truy cập mảng Java.

Chi phí theo mô hình RAM với thao tác `long` có độ rộng cố định: **O(log(mn))** thời gian, O(1) bộ nhớ phụ, nếu dữ liệu đã được bảo đảm sắp xếp row-major. **Không cần** tạo mảng ảo `int[m*n]`; việc thật sự làm phẳng bằng cách sao chép sẽ tốn O(mn) thời gian và bộ nhớ bổ sung.

## 6. Lựa chọn thuật toán và cách phân tích đúng

### 6.1. Độ phức tạp theo hai chiều

Kích thước ma trận thường phải mô tả bằng **hai tham số m và n**, không chỉ “N”. Ví dụ:

- **Quét toàn bộ:** O(mn).
- **Tìm nhị phân trên từng hàng:** O(m log(n+1)).
- **Staircase:** O(m+n).
- **Nhị phân row-major toàn cục:** O(log(mn+1)).

Nếu `m=1` và `n` rất lớn, tìm nhị phân trên một hàng có thể nhanh hơn staircase chạy từ góc; nếu `m` và `n` đều lớn, staircase thường hơn hẳn quét toàn bộ. Do đó không nói “staircase luôn nhanh hơn tìm nhị phân từng hàng” chỉ dựa vào tên thuật toán. Các cận khác nhau còn phụ thuộc vào hình dáng ma trận.

Nếu đề bài **bảo đảm thứ tự row-major toàn cục**, ta có thể dùng binary search O(log(mn)) thay vì staircase O(m+n). Nếu chỉ bảo đảm hàng/cột tăng, ưu tiên chiến lược đúng với bảo đảm đó; không được tự nâng giả thiết.

### 6.2. Tiền xử lý không miễn phí

Khi đầu vào **chưa** được sắp xếp mà ta quyết định sắp xếp dữ liệu:

- Sắp xếp từng hàng tốn chi phí riêng cho từng hàng và có thể làm thay đổi vị trí phần tử, nên chỉ số trả về sau khi sắp xếp không còn là chỉ số gốc.
- Sắp xếp toàn bộ `mn` phần tử rồi phân bố lại theo row-major có thể tốn O(mn log(mn)) phép so sánh theo thuật toán so sánh thông thường, cộng chi phí sao chép hoặc cấp phát nếu có.
- Chỉ với một truy vấn, quét O(mn) thường đơn giản hơn sắp xếp trước. Với rất nhiều truy vấn trên dữ liệu tĩnh, đầu tư tiền xử lý có thể có giá trị, nhưng phải cộng vào tổng chi phí.

Nếu đầu vào đã được **bảo đảm** có cấu trúc thứ tự, không cần kiểm tra lại từng ô cho mỗi truy vấn. Nếu muốn tự xác minh ma trận chữ nhật, một lần đi qua các m hàng tốn O(m). Nếu muốn tự kiểm tra mọi hàng và cột đã sắp xếp, thông thường phải xem O(mn) dữ liệu. Nếu chèn các bước kiểm tra này **vào bên trong** mỗi hàm tìm kiếm, độ phức tạp toàn hàm phải cộng thêm chi phí kiểm tra; bảng ở trên chỉ tính **bước tìm kiếm trên dữ liệu đã thỏa tiền điều kiện**.

### 6.3. Cần tìm kết quả nào?

- **Tồn tại hay không / một tọa độ bất kỳ:** staircase đủ dùng cho ma trận có hàng và cột không giảm; binary search đủ dùng cho row-major toàn cục.
- **Tọa độ đầu tiên theo thứ tự hàng trong ma trận row-major:** dùng lower bound toàn cục.
- **Tọa độ đầu tiên theo thứ tự hàng khi chỉ mỗi hàng được sắp xếp:** quét hàng từ trên xuống và lấy lower bound trong hàng đầu có target.
- **Đếm tất cả bản sao của target trong row-major toàn cục:** tìm vị trí lower bound target và upper bound (vị trí đầu tiên > target) trên dãy ảo rồi lấy hiệu hai vị trí; O(log(mn)).
- **Đếm tất cả bản sao với hàng/cột không giảm nhưng không row-major:** không dùng hiệu hai ranh giới trên dãy ảo chưa sắp xếp. Có thể xem xét đếm qua từng hàng bằng hai binary search rồi cộng lại; thời gian O(m log(n+1)).
- **Tìm kiếm theo nhiều loại truy vấn/cập nhật:** nếu ma trận thay đổi, phải duy trì bất biến thứ tự hoặc dùng cấu trúc dữ liệu khác. Khi cập nhật phá thứ tự, kết luận cắt bỏ hàng/cột không còn được bảo đảm.

## 7. Chương trình Java 17+ đầy đủ: ba dạng thứ tự

Chương trình sau triển khai ba phương thức theo ba tiền điều kiện khác nhau:

1. `findEachRowSorted`: chỉ yêu cầu mỗi hàng không giảm; trả tọa độ đầu tiên theo row-major.
2. `findStaircase`: yêu cầu cả hàng và cột đều không giảm; trả một tọa độ khớp bất kỳ.
3. `findFlatBinary`: yêu cầu toàn bộ row-major không giảm; dùng lower bound và trả tọa độ đầu tiên theo row-major.

**Tiền điều kiện chung:** mỗi ma trận truyền vào là mảng `int[][]` không null, các hàng không null và cùng chiều dài. Các hàm không quét để kiểm tra cấu trúc chữ nhật hoặc thứ tự, nhằm giữ nguyên độ phức tạp của riêng bước tìm kiếm. Nếu nhận dữ liệu không tin cậy, hãy kiểm tra hợp đồng tại đầu vào một lần trước khi thực hiện truy vấn; không sử dụng các hàm trên dữ liệu sai tiền điều kiện.

Lưu thành **`OrderedMatrixSearchDemo.java`**:

~~~java
public final class OrderedMatrixSearchDemo {
    record Cell(int row, int col) {}

    private static final Cell NOT_FOUND = new Cell(-1, -1);

    // Tiền điều kiện: ma trận chữ nhật; từng hàng không giảm.
    static Cell findEachRowSorted(int[][] matrix, int target) {
        for (int r = 0; r < matrix.length; r++) {
            int[] current = matrix[r];
            int n = current.length;

            if (n == 0 || target < current[0] || target > current[n - 1]) {
                continue;
            }

            int low = 0;
            int high = n;
            while (low < high) {
                int mid = low + (high - low) / 2;
                if (current[mid] < target) {
                    low = mid + 1;
                } else {
                    high = mid;
                }
            }

            if (low < n && current[low] == target) {
                return new Cell(r, low);
            }
        }
        return NOT_FOUND;
    }

    // Tiền điều kiện: ma trận chữ nhật; hàng và cột đều không giảm.
    static Cell findStaircase(int[][] matrix, int target) {
        int m = matrix.length;
        if (m == 0) {
            return NOT_FOUND;
        }
        int n = matrix[0].length;
        if (n == 0) {
            return NOT_FOUND;
        }

        int r = 0;
        int c = n - 1;
        while (r < m && c >= 0) {
            int value = matrix[r][c];
            if (value == target) {
                return new Cell(r, c);
            }
            if (value > target) {
                c--;
            } else {
                r++;
            }
        }
        return NOT_FOUND;
    }

    // Tiền điều kiện: ma trận chữ nhật; row-major không giảm.
    static Cell findFlatBinary(int[][] matrix, int target) {
        int m = matrix.length;
        if (m == 0) {
            return NOT_FOUND;
        }
        int n = matrix[0].length;
        if (n == 0) {
            return NOT_FOUND;
        }

        long total = (long) m * n;
        long low = 0;
        long high = total;

        // Lower bound trên dãy row-major ảo [0, total).
        while (low < high) {
            long mid = low + (high - low) / 2;
            int r = (int) (mid / n);
            int c = (int) (mid % n);
            int value = matrix[r][c];

            if (value < target) {
                low = mid + 1;
            } else {
                high = mid;
            }
        }

        if (low == total) {
            return NOT_FOUND;
        }
        int r = (int) (low / n);
        int c = (int) (low % n);
        return matrix[r][c] == target ? new Cell(r, c) : NOT_FOUND;
    }

    private static String format(Cell result) {
        return result.row() == -1
                ? "not found"
                : "(" + result.row() + "," + result.col() + ")";
    }

    public static void main(String[] args) {
        int[][] rowColumn = {
            {1, 4, 7, 11, 15},
            {2, 5, 8, 12, 19},
            {3, 6, 9, 16, 22},
            {10, 13, 14, 17, 24},
            {18, 21, 23, 26, 30}
        };

        int[][] global = {
            {1, 3, 5, 7},
            {10, 11, 16, 20},
            {23, 30, 34, 60}
        };

        int[][] rowsOnly = {
            {1, 4, 9, 13},
            {2, 3, 8, 11},
            {-5, 0, 7, 20}
        };

        int[][] duplicates = {
            {1, 2, 2},
            {2, 2, 4}
        };

        System.out.println("Row/column 5: "
                + format(findStaircase(rowColumn, 5)));
        System.out.println("Row/column 20: "
                + format(findStaircase(rowColumn, 20)));
        System.out.println("Global 3: "
                + format(findFlatBinary(global, 3)));
        System.out.println("Global 13: "
                + format(findFlatBinary(global, 13)));
        System.out.println("Rows only 7: "
                + format(findEachRowSorted(rowsOnly, 7)));
        System.out.println("Rows only 11: "
                + format(findEachRowSorted(rowsOnly, 11)));
        System.out.println("Duplicates first 2: "
                + format(findFlatBinary(duplicates, 2)));
        System.out.println("Duplicates staircase 2: "
                + format(findStaircase(duplicates, 2)));
        System.out.println("Empty: "
                + format(findStaircase(new int[0][0], 9)));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac OrderedMatrixSearchDemo.java
java OrderedMatrixSearchDemo
~~~

Kết quả chuẩn chính xác:

~~~text
Row/column 5: (1,1)
Row/column 20: not found
Global 3: (0,1)
Global 13: not found
Rows only 7: (2,2)
Rows only 11: (1,3)
Duplicates first 2: (0,1)
Duplicates staircase 2: (0,2)
Empty: not found
~~~

**Giải thích kết quả:**

- `rowColumn` có hàng/cột không giảm nhưng không row-major toàn cục. Staircase tìm số 5 ở hàng 1 cột 1; số 20 vắng mặt nên trả not found.
- `global` là row-major sorted. Binary search ánh xạ chỉ số ảo sang hàng/cột để tìm số 3 ở `(0,1)`; số 13 không xuất hiện.
- `rowsOnly` chỉ cần mỗi hàng tăng. Tìm 7 ở `(2,2)`, số 11 ở `(1,3)`.
- `duplicates` thỏa cả hai dạng thứ tự. Lower bound row-major xác định bản sao số 2 đầu tiên tại `(0,1)`; staircase trả ngay số 2 tại `(0,2)`. Cả hai đều hợp lệ cho yêu cầu “tìm một vị trí”; chỉ cách đầu tiên thỏa yêu cầu “vị trí đầu tiên theo row-major”.
- `new int[0][0]` có 0 hàng, nên không chứa giá trị nào. Với `new int[3][0]`, mỗi hàng có 0 cột và kết quả tìm kiếm cũng không tìm thấy.

**Bảo đảm hiệu năng của ba hàm trên:** chỉ tính thao tác tìm kiếm trên đầu vào thỏa hợp đồng; `findEachRowSorted` có O(m log(n+1)) cho n>0, `findStaircase` O(m+n), `findFlatBinary` O(log(mn+1)), đều O(1) bộ nhớ phụ. Việc in kết quả, xây dựng ma trận từ mã nguồn, xác minh cấu trúc và xác minh thứ tự nếu bổ sung là các chi phí riêng.

## 8. Ma trận rỗng, jagged array, trùng lặp và kiểm tra hợp đồng

### 8.1. Không nhầm ma trận 0 hàng với 0 cột

Java cho phép:

~~~java
int[][] noRows = new int[0][0]; // m=0
int[][] noColumns = new int[3][0]; // m=3, n=0
~~~

Cả hai không có ô dữ liệu. Hàm cần kiểm tra số hàng trước khi đọc `matrix[0]`, và kiểm tra số cột trước khi tính `c=n-1` hoặc lấy `mid/n`. Chia cho n khi n=0 gây lỗi `ArithmeticException`; truy cập `matrix[0]` khi m=0 gây `ArrayIndexOutOfBoundsException`.

### 8.2. Ma trận không chữ nhật cần hợp đồng riêng

Ví dụ:

~~~java
int[][] jagged = {
    {1, 3},
    {2},
    {4, 6, 8}
};
~~~

Đây là một `int[][]` Java hợp lệ nhưng **không phải ma trận chữ nhật**. Công thức `r = k/n` và `c = k%n` với n chung không còn biểu diễn đúng mọi ô. Staircase từ cột `n-1` cũng có thể truy cập ra ngoài giới hạn ở hàng ngắn hơn.

Nếu đầu vào có thể sai dạng, có thể kiểm tra một lần khi tiếp nhận dữ liệu:

~~~java
// Mã minh họa: đặt vào một lớp Java nếu cần sử dụng độc lập.
static void requireRectangular(int[][] matrix) {
    if (matrix == null) {
        throw new IllegalArgumentException("null matrix");
    }
    if (matrix.length == 0) {
        return;
    }
    if (matrix[0] == null) {
        throw new IllegalArgumentException("null row");
    }
    int n = matrix[0].length;
    for (int r = 1; r < matrix.length; r++) {
        if (matrix[r] == null || matrix[r].length != n) {
            throw new IllegalArgumentException("ragged matrix");
        }
    }
}
~~~

Kiểm tra độ dài hàng trên m hàng mất O(m) thời gian. Nếu cần kiểm tra từng hàng/cột thật sự không giảm, phải duyệt các phần tử liên quan, thường O(mn). Không khẳng định toàn hàm “O(log(mn))” nếu mỗi lần truy vấn đều tự quét O(mn) để kiểm tra giả thiết trước khi tìm.

Với jagged array mà **mỗi hàng độc lập đã sắp xếp**, vẫn có thể áp dụng tìm kiếm nhị phân từng hàng bằng chiều dài riêng của từng hàng. Nhưng quy ước ma trận chữ nhật, xử lý theo góc và ánh xạ chỉ số ảo phải được thiết kế lại.

### 8.3. Phần tử trùng nhau có hợp lệ không?

Có. Thứ tự **không giảm** cho phép các phần tử bằng nhau. Khi gặp `a[r][c] == target`, staircase có thể trả ngay vì tìm được **một vị trí hợp lệ**, nhưng không bảo đảm là vị trí nhỏ nhất theo hàng/cột.

Lower bound trên dãy ảo được bảo đảm row-major không giảm cho vị trí xuất hiện **đầu tiên**. Nếu cần **cuối cùng**, có thể tìm upper bound (vị trí đầu tiên lớn hơn target) rồi lấy chỉ số đứng trước, sau khi xác nhận target thực sự xuất hiện.

Nếu đề bảo đảm mọi giá trị **phân biệt** thì không có vấn đề nhiều tọa độ; tuy nhiên không được tự thêm giả thiết này khi chỉ được nói “tăng dần” trong ngôn ngữ tự nhiên mà chưa rõ là tăng nghiêm ngặt hay không giảm.

### 8.4. Thứ tự sắp xếp và bộ so sánh

Với các giá trị `int`, dùng `<`, `>` và `==` có ý nghĩa trực tiếp. Với đối tượng, chuỗi hoặc khóa ghép, phép so sánh dùng để xác định thứ tự của ma trận phải nhất quán với phép xác định có khớp hay không. Không áp dụng điều kiện cắt tỉa theo `Comparator` A nhưng lại quyết định mục tiêu bằng một quan hệ bằng nhau khác mà không có chứng minh.

Đối với các ô có giá trị rất lớn hoặc là chuỗi dài, một lần so sánh có thể không còn O(1) theo mô hình chi phí bit/ký tự. Khi ấy công thức số lượt so sánh vẫn đúng, nhưng thời gian phải nhân hoặc cộng thêm chi phí xử lý khóa.

## 9. Vì sao chiến lược sai có thể bỏ lỡ phần tử?

### 9.1. Dùng binary search toàn cục trên ma trận chỉ có hàng/cột tăng

Ma trận:

~~~text
1  4  7
2  5  8
3  6  9
~~~

là hợp lệ khi mỗi hàng và cột không giảm. Nhưng dãy row-major `[1,4,7,2,5,8,3,6,9]` không tăng. Khi target=2, binary search trên dãy ảo có thể bỏ qua vị trí có 2; cụ thể lower bound chuẩn với target = 2 trả chỉ số k = 1, trỏ tới giá trị 4 ở ô (0,1) chứ không phải giá trị 2 ở (1,0), nên báo “không thấy” nếu chỉ kiểm tra ô đó. Lỗi nằm ở **tiền điều kiện không thỏa**, không phải ở phép chia `k/n`.

### 9.2. Dùng staircase khi chỉ từng hàng tăng

Ma trận:

~~~text
1  4  9  13
2  3  8  11
-5  0  7  20
~~~

có mỗi hàng tăng nhưng cột đầu không tăng. Tại một góc, phép suy luận loại trừ một cột dựa trên việc “những ô phía dưới đều lớn hơn ô hiện tại” có thể sai. Ví dụ nếu target `8`, tại `(0,3)=13` có thể sang trái, nhưng việc bỏ các cột ở những bước khác không được bảo đảm đúng do cột không có trật tự. **Không sử dụng staircase** nếu chỉ đề cho sorted rows.

### 9.3. Chỉ kiểm tra đường chéo hoặc hình dáng giá trị

Một ma trận có góc trên trái là nhỏ nhất và góc dưới phải là lớn nhất **không đủ** để suy ra mỗi hàng/cột đều tăng. Không thể chỉ dựa vào bốn góc hoặc một vài ví dụ minh họa rồi khẳng định tính đơn điệu của mọi hàng/cột. Bất biến phải được đề bài quy định hoặc được kiểm tra một cách hợp lệ.

## 10. Phân tích thêm: nhiều truy vấn, cập nhật và hình dáng ma trận

Nếu có `q` truy vấn độc lập trên cùng một ma trận **không thay đổi**, không cần xây dựng cấu trúc mới cho các cách tìm kiếm ở trên:

- Ma trận row-major đã sắp xếp: **O(q log(mn+1))** thời gian cho q lần binary search.
- Ma trận có hàng/cột không giảm: **O(q(m+n))** thời gian cho q lần staircase.
- Ma trận chỉ có từng hàng không giảm: **O(qm log(n+1))** trong trường hợp xấu cho q lần tìm nhị phân theo từng hàng.

Các kết quả đó bỏ qua chi phí **đọc đầu vào** O(mn), xây dựng ma trận và xuất q đáp án. Nếu tính tất cả từ đầu, cộng các chi phí tương ứng.

Nếu số truy vấn rất lớn hoặc bài có dạng hỏi khác (đếm số phần tử ≤ x, tìm k phần tử nhỏ nhất, tọa độ đầu tiên, thay đổi giá trị...), có thể cân nhắc phương pháp tiền xử lý, chỉ mục hoặc khai thác cấu trúc đặc biệt. Nhưng không nên tạo một cấu trúc bổ sung chỉ vì một truy vấn đơn giản.

**Khi cập nhật một ô:** thay đổi `a[r][c]` có thể phá thứ tự hàng, cột hoặc row-major. Sau cập nhật, không thể tiếp tục dùng thuật toán dựa trên thứ tự nếu không chứng minh rằng tính chất đó vẫn được giữ. Ví dụ thay một phần tử giữa hàng bằng giá trị quá lớn có thể khiến chính hàng không còn không giảm; thay giá trị cuối hàng lên trên đầu hàng tiếp theo có thể phá điều kiện row-major dù các hàng riêng lẻ vẫn được sắp xếp.

**Ma trận rất dẹt hoặc rất cao:** với `m=1`, tìm nhị phân trên một hàng là O(log n); staircase từ góc có thể tốn O(n). Với `n=1`, tìm nhị phân toàn cục cho dãy một cột đã sắp xếp row-major là O(log m), trong khi staircase có thể tốn O(m). Vì vậy nên chọn phương pháp tận dụng **bảo đảm mạnh nhất thực sự có** và phù hợp với kích thước hai chiều.

## 11. Kiểm thử biên và bộ thử phản ví dụ

| Tình huống | Dữ liệu | Kết quả / điều kiện cần kiểm tra |
|---|---|---|
| Không có hàng | `new int[0][0]` | Không tìm thấy, không đọc `a[0]` |
| Có hàng nhưng 0 cột | `new int[3][0]` | Không tìm thấy, tránh chia cho 0 |
| Một ô khớp | `[[5]]`, target 5 | `(0,0)` |
| Một ô không khớp | `[[5]]`, target 6 | `(-1,-1)` |
| Một hàng đã sắp xếp | `[[1,3,5,9]]`, target 5 | `(0,2)`; binary search hợp lệ |
| Một cột đã sắp xếp | `[[1],[4],[7]]`, target 4 | `(1,0)` |
| Mảng có số âm và 0 | `[[-5,-1,0],[3,4,9]]` | So sánh nguyên thông thường |
| Trùng lặp row-major | `[[1,2,2],[2,2,4]]`, target 2 | Lower bound trả `(0,1)` |
| Hàng/cột không giảm nhưng không row-major | `[[1,4,7],[2,5,8],[3,6,9]]` | Chỉ staircase hoặc tìm từng hàng được bảo đảm |
| Chỉ từng hàng tăng | `[[1,4,9,13],[2,3,8,11],[-5,0,7,20]]` | Tìm từng hàng, không dùng staircase/binary toàn cục |
| Không có target, nhỏ hơn toàn ma trận | Ma trận tăng bất kỳ, target rất nhỏ | Trả không tìm thấy và không đọc ngoài biên |
| Không có target, lớn hơn toàn ma trận | Ma trận tăng bất kỳ, target rất lớn | Trả không tìm thấy |
| Target nằm ở góc | Ma trận có hàng/cột tăng, target ở góc trên phải | Staircase có thể trả ngay bước đầu |
| Ma trận có các hàng khác chiều dài | `[[1,3],[2],[4,6,8]]` | Không thỏa hợp đồng chữ nhật cho staircase/binary ảo |
| Kích thước khiến `m*n` vượt `int` | Ma trận lý thuyết lớn | Dùng phép nhân ép `long` trước |

**Kiểm thử theo tính chất (property-based idea):** với các ma trận nhỏ, hãy dùng quét toàn bộ làm lời giải tham chiếu cho bài toán **tồn tại**. Sinh dữ liệu thỏa từng bảo đảm thứ tự, chạy thuật toán tương ứng với nhiều target (trong và ngoài tập giá trị). Nếu thuật toán trả tọa độ, xác nhận tọa độ nằm trong giới hạn và ô đó bằng target; nếu trả không tìm thấy, xác nhận quét toàn bộ cũng không tìm thấy. Với lower bound, kiểm tra thêm không có tọa độ khớp nào đứng trước nó theo row-major.

Cách sinh ma trận kiểm thử cần giữ đúng bất biến:

- **Chỉ hàng tăng:** sinh độc lập từng hàng rồi sắp xếp riêng; cố ý tạo cột không tăng để bắt lỗi giả định quá mạnh.
- **Hàng và cột tăng:** có thể tạo mỗi ô không nhỏ hơn ô trên và ô trái, thêm bước tăng không âm; cố ý tạo ví dụ không row-major.
- **Row-major tăng:** sinh dãy tăng không giảm rồi phân phối liên tiếp vào từng hàng.

Nếu dùng ma trận **sai tiền điều kiện** để kiểm thử thuật toán đã tuyên bố chỉ nhận ma trận đã sắp xếp, đó là phép kiểm thử hợp đồng đầu vào, không phải phản chứng tính đúng của thuật toán trên miền hợp lệ. Tuy nhiên, phản ví dụ sai tiền điều kiện rất hữu ích để hiểu tại sao không được chọn thuật toán đó.

## 12. Lỗi phổ biến và cách tránh

1. **Đồng nhất “cả hàng và cột tăng” với “row-major tăng”.** Sự đảo thứ tự giữa cuối một hàng và đầu hàng tiếp theo khiến binary search toàn cục sai. Hãy kiểm tra điều kiện biên hàng nếu muốn áp dụng binary ảo.
2. **Dùng staircase trên ma trận chỉ tăng theo hàng.** Khi thiếu tính tăng trong cột, phép loại cả cột không có chứng minh.
3. **Bắt đầu sai góc rồi đi sai hướng.** Quy tắc trên-phải là `value>target → trái`, `value<target → xuống`; dưới-trái dùng `value>target → lên`, `value<target → phải`.
4. **Nhầm chỉ số của dãy ảo.** Đúng là `r=k/n` và `c=k%n` với n là **số cột**, không phải số hàng.
5. **Tràn số khi tính số ô.** `long total = m*n` vẫn có thể tràn int trước khi gán. Phải viết `(long)m*n`.
6. **Bỏ qua ma trận rỗng.** Đọc `matrix[0]` khi không có hàng, hoặc chia cho n khi n=0, gây lỗi chạy.
7. **Bỏ qua phần tử trùng.** Staircase trả một vị trí, không nhất thiết vị trí đầu tiên. Nếu cần đầu tiên theo row-major, dùng lower bound trên dữ liệu row-major hoặc tìm từng hàng đúng thứ tự.
8. **Nhầm tìm thấy với lower bound.** Vị trí đầu tiên có giá trị ≥ target không bảo đảm bằng target; cần kiểm tra equality.
9. **Dùng mảng Java bị lệch hàng.** `int[][]` không tự đảm bảo mọi hàng có cùng chiều dài. Kiểm tra/đặt hợp đồng rõ ràng.
10. **Gộp chi phí xác minh cấu trúc vào cận tìm kiếm rồi vẫn báo O(log(mn)).** Nếu mỗi truy vấn quét toàn ma trận để kiểm tra sorted, toàn bộ một truy vấn đã có O(mn) bước.
11. **Tự ý sắp xếp và quên tọa độ gốc.** Sau khi sắp xếp, vị trí phần tử có thể thay đổi; phải biết đề yêu cầu tọa độ trong ma trận nào.
12. **Dùng khái niệm “tăng dần” mơ hồ.** Hãy xác định tăng nghiêm ngặt hay không giảm, vì phần tử trùng ảnh hưởng cách trả kết quả.
13. **Tìm kiếm tuyến tính thay cho quy tắc loại trừ đã được chứng minh.** Quét toàn bộ vẫn đúng nhưng bỏ lỡ lợi thế khi ma trận có thứ tự; hãy đọc đặc tả để chọn cách nhanh hơn mà vẫn đúng.

### Checklist giải bài

- Ma trận có bao nhiêu hàng `m`, cột `n`, có chữ nhật và không null không?
- Đề bài **bảo đảm** mỗi hàng tăng, cả hàng/cột tăng hay toàn bộ row-major tăng?
- Cần một tọa độ bất kỳ, vị trí đầu tiên, số lần xuất hiện hay chỉ giá trị boolean?
- Có phần tử trùng không, quy tắc so sánh có nhất quán với thứ tự không?
- Khi loại bỏ một hàng/cột/nửa dãy ảo, bất biến nào chứng minh các ô bị loại không thể chứa đáp án?
- Công thức ánh xạ `k/n`, `k%n` và điều kiện biên `low<high` đã đúng chưa?
- Có xử lý `m=0`, `n=0`, một ô, không thấy target, target ở biên và phần tử trùng chưa?
- `m*n` có tràn `int` không, có ép `long` trước khi nhân không?
- Chi phí kiểm tra/sắp xếp đầu vào và nhiều truy vấn đã được tính riêng chưa?

**Kết luận:** “Ma trận có thứ tự” không tự xác định một thuật toán. **Chỉ hàng tăng** cho phép tìm nhị phân từng hàng; **hàng và cột tăng** cho phép cắt tỉa từ góc trong O(m+n); **toàn bộ row-major tăng** mới cho phép tìm nhị phân trên dãy ảo trong O(log(mn)). Lựa chọn đúng đến từ **tiền điều kiện và bất biến loại trừ**, không đến từ hình thức hai chiều của dữ liệu.
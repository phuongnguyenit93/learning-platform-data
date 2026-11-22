# Rút gọn chiều lưu trữ và điều kiện giữ đúng dữ liệu

**Rút gọn chiều lưu trữ trong quy hoạch động (dynamic programming space optimization)** là kỹ thuật thay một bảng trạng thái nhiều hàng/lớp bằng một hoặc vài hàng/lớp được tái sử dụng. Ví dụ, thay bảng `dp[i][c]` biểu diễn lời giải sau khi xét `i` phần tử ở dung lượng `c` bằng mảng một chiều `dp[c]`.

Ý tưởng này thường giảm **bộ nhớ phụ từ O(n·C) xuống O(C)**, nhưng **không phải lúc nào cũng hợp lệ**. Khi ghi kết quả mới vào một ô, ta có thể vô tình **ghi đè giá trị của lớp trước** mà một trạng thái khác vẫn cần đọc. Vì vậy, thứ tự cập nhật — **tăng dần, giảm dần hay dùng biến tạm** — là một phần của chứng minh tính đúng đắn, không chỉ là mẹo tối ưu.

Bài học thuộc chủ đề **Quy hoạch động** và tập trung vào bốn ví dụ nền tảng: **ba lô 0/1**, **ba lô không giới hạn**, **đếm đường đi lưới** và **xâu con chung không liên tiếp dài nhất (LCS)**. Mỗi ví dụ chỉ ra trạng thái phụ thuộc vào **hàng trước**, **hàng hiện tại** hay **ô chéo trước**, từ đó xác định phương án lưu và hướng quét an toàn.

## 1. Bản chất của một bảng quy hoạch động

Quy hoạch động lưu lời giải cho các **bài toán con** để tránh giải lặp. Khi có hai tham số, ta thường viết `F(i,j)`, ví dụ:

- `i`: số phần tử hoặc ký tự đã xét, hoặc hàng hiện tại.
- `j`: dung lượng, tổng tiền, cột lưới hoặc số ký tự tiền tố của chuỗi thứ hai.
- `F(i,j)`: kết quả tối ưu/số cách/tính khả thi ứng với hai tham số đó.

Một cài đặt trực tiếp cấp bảng:

```text
dp[0..n][0..C]
```

và lưu toàn bộ các hàng. Nhưng nếu công thức tính `F(i,j)` **chỉ đọc hàng i-1**, thì sau khi kết thúc hàng `i`, nhiều hàng cũ không còn cần thiết để **tính giá trị cuối**. Khi ấy có thể dùng:

- **Hai hàng (rolling rows):** `previous[j]`, `current[j]`; sau mỗi hàng đổi vai trò.
- **Một hàng (in-place rolling array):** cùng một mảng `dp[j]` chứa phần giá trị mới và phần giá trị cũ, được cập nhật theo thứ tự để không đọc nhầm.

**Câu hỏi quyết định không phải “có thể bỏ chiều i không?” mà là: sau khi cập nhật ô `dp[j]`, các bước tiếp theo cần giá trị cũ của ô đó hay không?**

### Sơ đồ phụ thuộc

Ví dụ công thức chỉ đọc hàng trước:

```text
F(i,j) <- F(i-1,j) and F(i-1,j-w)
```

Nếu cập nhật `j` **từ lớn xuống nhỏ** và `w>0`, thì `j-w<j`, ô `dp[j-w]` **chưa được ghi trong lượt i**; nó vẫn là `F(i-1,j-w)`. Ngược lại, nếu quét từ nhỏ lên lớn, ô `dp[j-w]` có thể đã thuộc hàng mới, thay đổi ý nghĩa công thức.

Một công thức khác:

```text
F(i,j) <- F(i-1,j) and F(i,j-w)
```

lại **cần ô cùng hàng đã được cập nhật**. Với `w>0`, quét `j` **từ nhỏ lên lớn** mới tạo đúng `F(i,j-w)`.

Vì thế, hai công thức trông rất giống nhau nhưng yêu cầu hướng duyệt **ngược nhau**.

## 2. Điều kiện cần trước khi rút gọn bộ nhớ

Một phép nén trạng thái phải trả lời đầy đủ các điểm sau:

1. **Định nghĩa trạng thái:** `dp[i][j]` mang ý nghĩa gì? Khi nén, `dp[j]` biểu diễn giá trị của lớp nào ở **từng thời điểm**?
2. **Quan hệ phụ thuộc:** công thức dùng `dp[i-1][j]`, `dp[i][j-1]`, `dp[i-1][j-1]`, nhiều lớp trước đó hay một miền rộng hơn?
3. **Hướng ghi:** sau khi cập nhật `dp[j]`, những ô chưa tính tiếp theo có còn cần **giá trị cũ** của `dp[j]` không?
4. **Biên/khởi tạo:** hàng `i=0`, dung lượng `j=0`, tổng bằng 0, xâu rỗng hoặc ô bị cấm có được khởi tạo đúng?
5. **Ý nghĩa dùng một lần hay nhiều lần:** cập nhật trạng thái có cho phép **dùng lại phần tử ở cùng lượt** hay không?
6. **Kết quả cần trả:** chỉ cần **giá trị tối ưu** hay còn phải **phục dựng các lựa chọn**? Có thể cần giữ bảng hoặc thông tin phụ để truy vết.
7. **Thời gian và số học:** số phép tính có giữ nguyên không, kiểu dữ liệu có đủ tránh tràn hay không?

Nếu một trạng thái phụ thuộc vào `i-2` thay vì chỉ `i-1`, một hàng có thể không đủ; đôi khi cần **hai hoặc ba lớp**. Nếu cần nhiều trạng thái không có thứ tự cập nhật an toàn, phải dùng thêm bộ đệm hoặc thiết kế lại thuật toán. Nén bộ nhớ **không phải** lúc nào cũng chuyển mọi DP hai chiều thành một chiều được.

## 3. Ba lô 0/1: bắt buộc quét dung lượng giảm dần

**Bài toán:** có `n` món hàng, mỗi món `i` có trọng lượng nguyên dương `w_i` và giá trị không âm `v_i`. Mỗi món được chọn **tối đa một lần**. Với sức chứa nguyên không âm `C`, tìm tổng giá trị lớn nhất mà tổng trọng lượng không vượt `C`.

Định nghĩa `F(i,c)` là giá trị tối ưu khi chỉ được chọn trong **i món đầu**, sức chứa `c`. Khi không xét món nào hoặc dung lượng bằng 0 (trọng lượng các món đều dương), giá trị là 0.

Công thức:

```text
F(0,c) = 0                 for all c in [0,C]

F(i,c) =
    F(i-1,c)               if w_i > c
    max(
        F(i-1,c),
        v_i + F(i-1,c-w_i)
    )                       if w_i <= c
```

Hai khả năng là **không chọn món i** hoặc **chọn món i đúng một lần**. Cả hai đều phụ thuộc vào hàng `i-1`; đặc biệt khi chọn món i, phần dung lượng còn lại phải được giải bằng **những món trước i**, không được tiếp tục dùng chính món i.

### Nén từ bảng hai chiều sang một chiều

Khởi tạo `dp[0..C]=0`. Với từng món `(w_i,v_i)`, quét **`c=C,C-1,...,w_i`**:

```text
ALGORITHM ZERO_ONE_KNAPSACK_1D(items, C)
    dp[0..C] <- 0

    FOR EACH item (weight, value) IN items DO
        FOR c FROM C DOWNTO weight DO
            dp[c] <- MAX(dp[c], value + dp[c-weight])
        END FOR
    END FOR

    RETURN dp[C]
END ALGORITHM
```

**Bất biến quan trọng:** trước khi xử lý món `i`, `dp[c]=F(i-1,c)` với mọi `c`. Trong vòng quét giảm dần, tại lúc cập nhật `dp[c]`:

- `dp[c]` vẫn là `F(i-1,c)`, vì chỉ các chỉ số **lớn hơn c** mới được cập nhật.
- `dp[c-w_i]` vẫn là `F(i-1,c-w_i)`, vì `w_i>0` và `c-w_i<c`, tức ô này **chưa đến lượt cập nhật**.
- Gán `dp[c]=max(...)` vì thế đúng bằng `F(i,c)`.

Sau khi quét xong tất cả c, mảng chứa `F(i,c)`. Quy nạp theo i chứng minh mảng cuối cùng đúng. Không cần giữ toàn bộ bảng.

### Phản ví dụ nếu quét tăng dần

Chỉ có **một món** `(weight=3,value=5)`, sức chứa `C=6`.

Với 0/1 knapsack, món này chỉ có thể lấy một lần, nên tối ưu là **5**, không phải 10.

Nếu quét **tăng dần**:

```text
initial: dp[0..6] = [0,0,0,0,0,0,0]

c=3: dp[3] = max(0, 5 + dp[0]) = 5
c=4: dp[4] = 5
c=5: dp[5] = 5
c=6: dp[6] = max(0, 5 + dp[3]) = 10   // SAI 0/1!
```

Ở c=6, `dp[3]` đã được cập nhật trong **chính lượt của món đang xét**, nên phép tính đã dùng món đó **lần thứ hai**. Quét tăng dần đã vô tình chuyển ngữ nghĩa thành cho phép **lặp lại cùng một món**.

**Hướng đúng cho 0/1: giảm dần.** Đây là ràng buộc ngữ nghĩa, không phải mẹo tăng tốc.

## 4. Mô phỏng ba lô 0/1 với nhiều món

Cho ba món:

| Món | Trọng lượng | Giá trị |
| --- | ---: | ---: |
| A | 2 | 4 |
| B | 3 | 5 |
| C | 4 | 7 |

Sức chứa `C=6`. Bảng một chiều `dp[c]` cho c từ 0 đến 6:

```text
Ban đầu:         [0,0,0,0,0,0,0]
Sau món A (2,4): [0,0,4,4,4,4,4]
Sau món B (3,5): [0,0,4,5,5,9,9]
Sau món C (4,7): [0,0,4,5,7,9,11]
```

Đáp án `dp[6]=11`, tương ứng với chọn A và C: tổng trọng lượng `2+4=6`, tổng giá trị `4+7=11`.

Không thể chọn hai món A trong 0/1 knapsack, dù trọng lượng của chúng có thể vẫn vừa sức chứa. Đây là ví dụ giúp phát hiện hướng quét sai: nếu cài đặt trả 12 (ba lần chọn A), thuật toán đã cho phép tái sử dụng món và **không còn giải bài 0/1**.

### Độ phức tạp và giới hạn

- Bảng hai chiều: **O(n·C)** thời gian và **O(n·C)** bộ nhớ.
- Bảng một chiều: **O(n·C)** thời gian và **O(C)** bộ nhớ.
- Nén bộ nhớ không làm giảm số trạng thái `(i,c)` được tính theo mô hình này; nó chỉ tránh lưu những hàng không còn cần thiết.
- Đây cũng là thuật toán **giả đa thức**, vì C là **giá trị số** chứ không phải số bit biểu diễn C.

Nếu mỗi trọng lượng `w_i>0` nhưng giá trị `v_i=0`, phép cập nhật vẫn đúng. Nếu có trọng lượng bằng 0 hoặc âm, cần xem lại đặc tả và vòng lặp; chương trình minh họa **từ chối trọng lượng không dương** để giữ bất biến và tránh các trường hợp đặc biệt.

## 5. Ba lô không giới hạn: quét dung lượng tăng dần

**Unbounded knapsack** cũng có trọng lượng và giá trị, nhưng **mỗi loại món có thể chọn nhiều lần**. Định nghĩa `U(i,c)` là tối ưu với i loại món đầu, sức chứa c.

Công thức khi `w_i<=c`:

```text
U(i,c) = max(
    U(i-1,c),                // Không chọn loại i
    v_i + U(i,c-w_i)         // Chọn loại i, có thể chọn tiếp i
)
```

Khác biệt quan trọng: phần trạng thái sau khi chọn món `i` là **`U(i,c-w_i)` của chính hàng i**, không phải hàng trước! Vì vậy, ở bảng một chiều, khi xử lý loại món `i` phải quét **`c=w_i,w_i+1,...,C` tăng dần**:

```text
ALGORITHM UNBOUNDED_KNAPSACK_1D(items, C)
    dp[0..C] <- 0

    FOR EACH item type (weight, value) IN items DO
        FOR c FROM weight TO C DO
            dp[c] <- MAX(dp[c], value + dp[c-weight])
        END FOR
    END FOR

    RETURN dp[C]
END ALGORITHM
```

**Bất biến:** ngay trước lượt loại i, `dp[c]=U(i-1,c)`. Khi quét tăng dần, `dp[c]` vẫn là giá trị **hàng trước**, còn `dp[c-weight]` đã là **hàng hiện tại** vì `weight>0`. Nhờ vậy, phép cập nhật tương ứng chính xác với công thức unbounded.

Nếu dùng vòng giảm dần như 0/1, thuật toán sẽ **không cho loại i tự dùng lại trong cùng lượt**, có thể trả đáp án sai.

Với ba loại A, B, C ở mục 4 và `C=6`, unbounded knapsack có thể chọn **ba món A**:

`2+2+2=6`, tổng giá trị `4+4+4=12`.

Vì vậy kết quả **12**, cao hơn kết quả 0/1 là **11**. Chỉ thay đổi **thứ tự quét** đã thay đổi **định nghĩa bài toán được giải**.

| Thuộc tính | 0/1 knapsack | Unbounded knapsack |
| --- | --- | --- |
| Mỗi món/loại | Chọn tối đa một lần | Chọn không giới hạn lần |
| Nguồn khi chọn món i | `F(i-1,c-w_i)` | `U(i,c-w_i)` |
| Quét c ở bảng 1D | **Giảm dần** | **Tăng dần** |
| Kết quả với A=(2,4), B=(3,5), C=(4,7), C=6 | 11 | 12 |
| Thời gian/bộ nhớ | O(nC) / O(C) | O(nC) / O(C) |

**Lưu ý:** ở đây `C` trong dòng mô tả là **sức chứa**, còn A/B/C trong tên món là các nhãn ví dụ. Không nhầm hai ý nghĩa khác nhau của ký tự C.

## 6. Bài toán tổng con 0/1: cùng nguyên tắc giảm dần

Bài toán **subset sum** hỏi có chọn được **một tập con**, mỗi phần tử dùng nhiều nhất một lần, để tổng đúng `target` hay không.

Với dãy số nguyên **dương**, định nghĩa `possible[i][s]`: có dùng một số trong i phần tử đầu để tạo đúng tổng s không? Công thức:

```text
possible[i][s] =
    possible[i-1][s]
    OR (s >= x_i AND possible[i-1][s-x_i])
```

Dòng gốc `possible[0][0]=true`, các s>0 là false.

Nén thành `boolean[] dp`, ta cũng phải quét **s từ target về x_i**:

```text
ALGORITHM SUBSET_SUM_01(numbers, target)
    dp[0] <- true
    dp[1..target] <- false

    FOR EACH positive number x IN numbers DO
        FOR s FROM target DOWNTO x DO
            dp[s] <- dp[s] OR dp[s-x]
        END FOR
    END FOR

    RETURN dp[target]
END ALGORITHM
```

**Phản ví dụ quét tăng:** dãy `[3,5]`, mục tiêu 6. Không có tập con nào bằng 6: `0,3,5,8` là các tổng khả dĩ. Nhưng nếu quét **tăng dần** với phần tử 3, `dp[3]` trở thành true rồi `dp[6]` cũng trở thành true từ chính `dp[3]`: thuật toán đã **dùng số 3 hai lần**. Hướng giảm dần trả **false** đúng.

Ngược lại, với mục tiêu 8, `3+5=8` là hợp lệ; DP giảm dần trả **true**. Với `target=0`, tập con rỗng là lời giải và kết quả true.

Không áp dụng nguyên xi cách duyệt `0..target` này cho các số **âm**: miền tổng có thể âm, cần một thiết kế trạng thái khác (offset, tập các tổng đạt được hoặc cấu trúc phù hợp).

## 7. Đếm đường đi trên lưới: vì sao cần quét từ trái sang phải?

Xét lưới có `R` hàng, `C` cột, tất cả ô đều đi được. Bắt đầu từ ô trên trái `(0,0)`, đi **xuống** hoặc **sang phải** mỗi bước, cần đếm số đường đến ô dưới phải `(R-1,C-1)`.

Đặt `G(r,c)` là số cách tới ô `(r,c)`. Công thức:

```text
G(0,0) = 1

G(r,c) = G(r-1,c) + G(r,c-1)
         (cộng 0 cho các hướng vượt biên)
```

Bảng đầy đủ có O(RC) ô. Khi xử lý hàng r, ta chỉ cần **ô trên** `G(r-1,c)` và **ô bên trái của hàng hiện tại** `G(r,c-1)`. Do đó có thể lưu một hàng:

```text
ways[0..C-1] <- 0
ways[0] <- 1

FOR r FROM 0 TO R-1 DO
    FOR c FROM 1 TO C-1 DO
        ways[c] <- ways[c] + ways[c-1]
    END FOR
END FOR

RETURN ways[C-1]
```

Trong phép cập nhật **từ trái sang phải**:

- `ways[c]` chưa sửa trong hàng r nên là **giá trị phía trên** `G(r-1,c)`.
- `ways[c-1]` đã được sửa trong hàng r nên là **giá trị bên trái** `G(r,c-1)`.

Điều này thực hiện đúng công thức. Nếu quét từ phải sang trái, `ways[c-1]` có thể vẫn thuộc hàng **trước**, khiến kết quả sai.

Ví dụ lưới **3×4**:

```text
Khởi tạo:      [1,0,0,0]
Sau hàng 0:    [1,1,1,1]
Sau hàng 1:    [1,2,3,4]
Sau hàng 2:    [1,3,6,10]

Số đường: 10
```

Đếm đường đi dạng này tốn **O(R·C)** thời gian, **O(C)** bộ nhớ thay vì O(R·C) nếu giữ cả bảng. Với R hoặc C bằng 0, bài toán không có ô bắt đầu/đích; trong chương trình minh họa trả **0**. Với lưới chỉ một hàng hoặc một cột không có vật cản, chỉ có **1 đường**.

**Lưu ý số học:** số đường có thể tăng rất nhanh. Chương trình Java dùng `long` và `Math.addExact` để phát hiện tràn khi giá trị vượt miền `long`; nếu bài yêu cầu đếm chính xác cho lưới lớn, dùng `BigInteger` hoặc phép chia dư theo modulo được đề bài chỉ định.

### Nếu lưới có vật cản?

Khi ô `(r,c)` bị chặn, cần gán `ways[c]=0` **ngay tại hàng hiện tại** trước khi tính các ô tiếp theo. Nếu không, giá trị đường đi từ hàng trước còn lưu trong ô bị chặn có thể bị dùng sai. Hướng quét trái sang phải vẫn đúng cho các ô còn lại, nhưng phải khởi tạo ô đầu và xử lý vật cản đầu/cuối nhất quán.

Đây là ví dụ khác của điều kiện **“đọc đúng lớp, ghi đúng thời điểm”**: không chỉ chọn chiều duyệt mà còn phải xử lý các trạng thái đặc biệt trước khi giá trị cũ bị dùng lại.

## 8. LCS: một hàng chưa đủ nếu không giữ ô chéo cũ

**LCS (longest common subsequence)** của hai chuỗi là dãy ký tự dài nhất xuất hiện theo đúng thứ tự tương đối trong cả hai chuỗi, nhưng **không cần liên tiếp**. LCS khác **longest common substring**, vốn yêu cầu ký tự liên tiếp.

Cho chuỗi `a` dài `m` và `b` dài `n`. Định nghĩa `L(i,j)` là độ dài LCS giữa **i ký tự đầu của a** và **j ký tự đầu của b**:

```text
L(0,j) = 0
L(i,0) = 0

If a[i-1] == b[j-1]:
    L(i,j) = L(i-1,j-1) + 1
Else:
    L(i,j) = max(L(i-1,j), L(i,j-1))
```

Mỗi ô có thể cần **ba phụ thuộc**:

| Phụ thuộc | Ý nghĩa |
| --- | --- |
| `L(i-1,j)` | Ô **trên**, thuộc hàng trước. |
| `L(i,j-1)` | Ô **trái**, thuộc hàng hiện tại. |
| `L(i-1,j-1)` | Ô **chéo trên trái**, thuộc hàng trước. |

Nếu cập nhật `dp[j]` từ trái sang phải, trước khi ghi `dp[j]`:

- `dp[j]` vẫn chứa **ô trên** `L(i-1,j)`.
- `dp[j-1]` đã chứa **ô trái** `L(i,j-1)`.
- Nhưng **`dp[j-1]` cũ**, tức ô chéo `L(i-1,j-1)`, đã bị ghi đè.

Vì vậy, phải dùng biến tạm `diagonal` để giữ ô chéo cũ; biến `oldUp` lưu `dp[j]` trước khi nó bị cập nhật để trở thành diagonal cho vòng kế tiếp.

```text
ALGORITHM LCS_LENGTH_ONE_ROW(a, b)
    dp[0..LENGTH(b)] <- 0

    FOR i FROM 1 TO LENGTH(a) DO
        diagonal <- 0

        FOR j FROM 1 TO LENGTH(b) DO
            oldUp <- dp[j]       // L(i-1,j)

            IF a[i-1] = b[j-1] THEN
                dp[j] <- diagonal + 1
            ELSE
                dp[j] <- MAX(dp[j], dp[j-1])
            END IF

            diagonal <- oldUp     // L(i-1,j) cho cột j+1
        END FOR
    END FOR

    RETURN dp[LENGTH(b)]
END ALGORITHM
```

**Bất biến vòng trong:** ngay trước khi xử lý cột j của hàng i, `dp[j]` là ô trên, `dp[j-1]` là ô trái mới và `diagonal` là ô chéo cũ. Nhờ vậy ta tính được `L(i,j)` đúng, rồi chuyển `oldUp` thành đường chéo của cột tiếp theo.

Ví dụ `a="ABCBDAB"`, `b="BDCABA"`, độ dài LCS là **4**; một LCS hợp lệ là `"BCBA"` hoặc `"BDAB"`. Chương trình ở mục 10 trả **4**, không nhất thiết phục dựng một chuỗi LCS cụ thể.

**Chi phí:** O(m·n) thời gian, O(n) bộ nhớ nếu dùng mảng theo chiều của b. Nếu mục tiêu chỉ là **độ dài**, có thể chọn chuỗi **ngắn hơn** làm trục cột để dùng O(min(m,n)) bộ nhớ; nếu cần phục dựng **chính chuỗi LCS**, cần lưu thêm thông tin hoặc dùng phương pháp phục dựng ít bộ nhớ phức tạp hơn.

**Giới hạn ví dụ Java:** `String.charAt` làm việc theo **đơn vị UTF-16**, nên mã dưới đây tính LCS trên các đơn vị `char`. Điều này phù hợp với chuỗi ASCII trong ví dụ. Nếu bài toán định nghĩa phần tử là Unicode **code point** hay **ký tự hiển thị (grapheme cluster)**, cần xác định lại đơn vị so sánh trước khi áp dụng nguyên xi mã.

## 9. Khác biệt giữa giá trị cuối và đường đi lời giải

Rút gọn từ `dp[i][j]` xuống `dp[j]` thường giữ đủ thông tin để tính **giá trị tối ưu cuối cùng**. Nhưng bảng đầy đủ còn hỗ trợ **truy vết đường đi**:

- Với **0/1 knapsack**, muốn liệt kê chính xác những món được chọn, cách phổ biến là xem `F(i,c)` có khác `F(i-1,c)` hay không, rồi lùi i và c. Nếu đã xóa mọi hàng trước, việc truy vết trực tiếp không còn đơn giản.
- Với **LCS**, muốn xây dựng chuỗi con chung, việc truy dấu thường cần so sánh các ô trên/trái/chéo của nhiều hàng.
- Với **đếm đường đi**, nếu chỉ cần số cách tới đích thì một hàng đủ; nếu muốn liệt kê mọi đường hoặc phục dựng một đường có ràng buộc riêng, cần thêm cơ chế lưu lựa chọn.

**Không nên lưu một mảng `parent[c]` đơn giản rồi mặc nhiên tin nó luôn phục dựng đúng nghiệm 0/1.** Một giá trị `dp[c]` có thể đã được tính ở một lượt trước, trong khi `parent[c-w]` sau đó bị cập nhật ở lượt khác; chuỗi parent có thể trộn các lớp và mô tả việc dùng một món quá một lần. Muốn truy vết đúng cần quản lý **thời điểm/lớp của predecessor** hoặc dùng bảng quyết định/chiến lược tính lại phù hợp.

Một số lựa chọn:

1. **Giữ bảng đầy đủ** khi cần truy vết và dung lượng bộ nhớ cho phép.
2. **Lưu quyết định** bằng cấu trúc phụ có chứng minh đúng, có thể ít bộ nhớ hơn bảng đầy đủ tùy bài.
3. **Tính lại các đoạn DP khi phục dựng** để đổi bộ nhớ lấy thời gian.
4. Với LCS, **Hirschberg** là ví dụ về chia để trị kết hợp DP theo hàng giúp phục dựng LCS với bộ nhớ tuyến tính theo chiều ngắn hơn, nhưng cần tổ chức thuật toán khác so với chỉ trả độ dài.

Rút gọn bộ nhớ không được làm thay đổi **yêu cầu đầu ra** của bài toán. Nếu đề bắt buộc xuất đường đi/lựa chọn, không thể chỉ trả giá trị rồi gọi là đã giải xong.

## 10. Chương trình Java 17+ hoàn chỉnh

Tệp `RollingDpDemo.java` cài đặt các ví dụ:

- Bảng **2D** và mảng **1D** cho 0/1 knapsack, dùng để kiểm tra cùng kết quả.
- Bản **1D quét tăng** cho unbounded knapsack.
- Subset sum 0/1 với mảng boolean **quét giảm**.
- Đếm đường đi lưới với mảng một chiều **quét trái sang phải**.
- LCS dùng một hàng và biến `diagonal` giữ ô chéo cũ.

Mã dùng `long` cho giá trị ba lô và số đường đi; giá trị vật phẩm phải không âm, trọng lượng phải dương. Các ví dụ nhỏ có kết quả không gây tràn; đếm đường đi sử dụng `Math.addExact` để báo tràn nếu có.

```java
import java.util.Objects;

public class RollingDpDemo {

    private static void validateItems(
            int[] weights, int[] values, int capacity) {
        Objects.requireNonNull(weights, "weights");
        Objects.requireNonNull(values, "values");
        if (capacity < 0 || weights.length != values.length) {
            throw new IllegalArgumentException(
                    "Capacity and item lengths must be valid");
        }
        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException(
                        "Weights positive, values nonnegative");
            }
        }
    }

    public static long zeroOneKnapsack2D(
            int[] weights, int[] values, int capacity) {
        validateItems(weights, values, capacity);
        int n = weights.length;
        long[][] dp = new long[n + 1][capacity + 1];

        for (int i = 1; i <= n; i++) {
            int weight = weights[i - 1];
            int value = values[i - 1];

            for (int c = 0; c <= capacity; c++) {
                long best = dp[i - 1][c];
                if (weight <= c) {
                    best = Math.max(best,
                            value + dp[i - 1][c - weight]);
                }
                dp[i][c] = best;
            }
        }
        return dp[n][capacity];
    }

    public static long zeroOneKnapsack1D(
            int[] weights, int[] values, int capacity) {
        validateItems(weights, values, capacity);
        long[] dp = new long[capacity + 1];

        for (int i = 0; i < weights.length; i++) {
            int weight = weights[i];
            int value = values[i];

            // 0/1: giảm dần để không dùng lại món hiện tại.
            for (int c = capacity; c >= weight; c--) {
                dp[c] = Math.max(dp[c], value + dp[c - weight]);
            }
        }
        return dp[capacity];
    }

    public static long unboundedKnapsack1D(
            int[] weights, int[] values, int capacity) {
        validateItems(weights, values, capacity);
        long[] dp = new long[capacity + 1];

        for (int i = 0; i < weights.length; i++) {
            int weight = weights[i];
            int value = values[i];

            // Không giới hạn: tăng dần để cho phép dùng tiếp loại i.
            for (int c = weight; c <= capacity; c++) {
                dp[c] = Math.max(dp[c], value + dp[c - weight]);
            }
        }
        return dp[capacity];
    }

    public static boolean subsetSum01(int[] numbers, int target) {
        Objects.requireNonNull(numbers, "numbers");
        if (target < 0) {
            throw new IllegalArgumentException("Negative target");
        }
        for (int number : numbers) {
            if (number <= 0) {
                throw new IllegalArgumentException(
                        "Only positive numbers supported");
            }
        }

        boolean[] possible = new boolean[target + 1];
        possible[0] = true;

        for (int number : numbers) {
            for (int s = target; s >= number; s--) {
                possible[s] |= possible[s - number];
            }
        }
        return possible[target];
    }

    public static long gridPaths1D(int rows, int cols) {
        if (rows < 0 || cols < 0) {
            throw new IllegalArgumentException("Negative grid size");
        }
        if (rows == 0 || cols == 0) {
            return 0;
        }

        long[] ways = new long[cols];
        ways[0] = 1;

        for (int row = 0; row < rows; row++) {
            // Giá trị cũ ở cột c là số đường từ ô phía trên.
            for (int col = 1; col < cols; col++) {
                ways[col] = Math.addExact(ways[col], ways[col - 1]);
            }
        }
        return ways[cols - 1];
    }

    public static int lcsLength1D(String a, String b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        int[] dp = new int[b.length() + 1];

        for (int i = 1; i <= a.length(); i++) {
            int diagonal = 0;
            for (int j = 1; j <= b.length(); j++) {
                int oldUp = dp[j];

                if (a.charAt(i - 1) == b.charAt(j - 1)) {
                    dp[j] = diagonal + 1;
                } else {
                    dp[j] = Math.max(dp[j], dp[j - 1]);
                }
                diagonal = oldUp;
            }
        }
        return dp[b.length()];
    }

    public static void main(String[] args) {
        int[] weights = {2, 3, 4};
        int[] values = {4, 5, 7};
        int capacity = 6;

        System.out.println("knapsack2D=" +
                zeroOneKnapsack2D(weights, values, capacity));
        System.out.println("knapsack1D=" +
                zeroOneKnapsack1D(weights, values, capacity));
        System.out.println("unbounded=" +
                unboundedKnapsack1D(weights, values, capacity));
        System.out.println("emptyItems=" +
                zeroOneKnapsack1D(new int[0], new int[0], 6));
        System.out.println("zeroCapacity=" +
                zeroOneKnapsack1D(weights, values, 0));

        int[] numbers = {3, 5};
        System.out.println("subset6=" + subsetSum01(numbers, 6));
        System.out.println("subset8=" + subsetSum01(numbers, 8));
        System.out.println("subset0=" + subsetSum01(numbers, 0));

        System.out.println("grid3x4=" + gridPaths1D(3, 4));
        System.out.println("grid1x5=" + gridPaths1D(1, 5));
        System.out.println("grid0x4=" + gridPaths1D(0, 4));

        System.out.println("lcsExample=" +
                lcsLength1D("ABCBDAB", "BDCABA"));
        System.out.println("lcsRepeat=" +
                lcsLength1D("AAAA", "AA"));
        System.out.println("lcsEmpty=" +
                lcsLength1D("", "ABC"));
    }
}
```

Biên dịch và chạy:

```bash
javac RollingDpDemo.java
java RollingDpDemo
```

**Đầu ra chính xác:**

```text
knapsack2D=11
knapsack1D=11
unbounded=12
emptyItems=0
zeroCapacity=0
subset6=false
subset8=true
subset0=true
grid3x4=10
grid1x5=1
grid0x4=0
lcsExample=4
lcsRepeat=2
lcsEmpty=0
```

**Cách đối chiếu:**

- `knapsack2D` và `knapsack1D` cùng trả **11**, xác nhận hướng quét giảm của bản 1D bảo toàn ngữ nghĩa 0/1 với dữ liệu thử.
- `unbounded=12` vì có thể lấy ba lần món `(2,4)`; không được xem 12 là kết quả hợp lệ của 0/1 knapsack.
- `emptyItems` và `zeroCapacity` đều 0 vì không có món được chọn hợp lệ trong hai tình huống đã nêu.
- `subset6=false`, bởi `3+3` là tái sử dụng sai một phần tử; `subset8=true` vì `3+5` hợp lệ. `subset0=true` vì tập con rỗng có tổng 0.
- `grid3x4=10` đúng theo ba hàng cộng dồn; lưới một hàng có 1 cách, còn lưới không có hàng có 0 cách.
- LCS của `"ABCBDAB"` và `"BDCABA"` dài 4; hai chuỗi `"AAAA"`, `"AA"` có LCS dài 2; nếu một chuỗi rỗng thì LCS dài 0.

Bốn phương pháp 1D không sửa các mảng đầu vào. Việc dùng một hàng là thuộc tính của **trạng thái trung gian**, không phải vì đề bài chỉ có một chiều.

## 11. Bảng nhận diện hướng quét an toàn

| Bài toán | Phụ thuộc cần giữ | Hướng quét 1D | Lý do |
| --- | --- | --- | --- |
| Ba lô **0/1** | `F(i-1,c)`, `F(i-1,c-w)` | **c giảm dần** | `dp[c-w]` vẫn là hàng trước, không dùng lại món i. |
| **Subset sum 0/1** | `P(i-1,s)`, `P(i-1,s-x)` | **s giảm dần** | Không dùng lại số x trong cùng lượt. |
| Ba lô **không giới hạn** | `U(i-1,c)`, `U(i,c-w)` | **c tăng dần** | `dp[c-w]` đã thuộc hàng hiện tại, cho phép lấy lại món i. |
| **Đếm đường đi lưới** | `G(r-1,c)`, `G(r,c-1)` | **c tăng dần** | Đọc ô trên cũ và ô trái mới. |
| **LCS** | Ô trên, trái và chéo cũ | **j tăng dần**, giữ `diagonal` | Ô chéo từ hàng trước đã bị ghi đè nếu không lưu riêng. |

Bảng này áp dụng với **các công thức và miền dữ liệu đã nêu**. Nếu bài toán thay đổi thành “có thể lấy tối đa K món mỗi loại”, “di chuyển theo nhiều hướng” hoặc “phụ thuộc hai hàng trước”, hướng quét phải được thiết kế lại từ đồ thị phụ thuộc, không sao chép máy móc.

## 12. Các lỗi phổ biến

1. **Duyệt 0/1 knapsack từ nhỏ lên lớn** rồi vô tình lấy một món nhiều lần.
2. **Duyệt unbounded knapsack từ lớn xuống nhỏ** khiến bản 1D không thể dùng lại loại món trong lượt hiện tại.
3. **Không viết rõ ý nghĩa `dp[c]` theo thời điểm.** Một ô có thể là hàng cũ hoặc hàng mới giữa vòng quét; không được dùng lẫn.
4. **Không kiểm tra điều kiện `weight>0`.** Chỉ số `c-weight` và chứng minh tiến triển dựa trên giả thiết này trong các ví dụ.
5. **Quên `dp[0]=true` ở subset sum.** Tập con rỗng tạo tổng 0 là cơ sở cho mọi lựa chọn.
6. **Dùng số âm trong subset sum dạng mảng `0..target`** mà không đổi miền chỉ số.
7. **Quét đường đi lưới từ phải sang trái** khiến ô `ways[c-1]` không phải giá trị của hàng hiện tại.
8. **Không đặt ô lưới bị chặn về 0 ngay đúng hàng** và vô tình đưa số đường cũ qua vật cản.
9. **Ở LCS, dùng `dp[j-1]` cho ô chéo cũ** sau khi nó đã được cập nhật, cho kết quả sai.
10. **Quên cập nhật `diagonal=oldUp` sau mỗi cột** khiến ô chéo ở vòng kế tiếp không đúng.
11. **Chỉ quan tâm giá trị tối ưu nhưng đề bài cần xuất danh sách món/đường đi.** Một hàng có thể không đủ để phục dựng nghiệm.
12. **Gọi O(C) là O(1) bộ nhớ.** C là tham số đầu vào; nén từ O(nC) xuống O(C) vẫn là bộ nhớ tăng theo C.
13. **Bỏ qua tràn số.** Số đường đi hoặc tổng giá trị có thể vượt `int`, thậm chí vượt `long`.
14. **Chuyển trạng thái sang “một hàng” khi còn phụ thuộc từ hàng i-2.** Có thể cần giữ nhiều lớp hoặc thiết kế lại.
15. **Nhầm LCS với common substring.** LCS cho phép các ký tự không liền nhau và dùng công thức khác.
16. **Cho rằng nén bộ nhớ luôn làm thuật toán nhanh hơn.** Số trạng thái tính thường không đổi; lợi ích chính là giảm lưu trữ, đôi khi còn ảnh hưởng khả năng truy vết.

## 13. Bài tập tự kiểm tra có lời giải

**Câu 1.** Một món trọng lượng 3, giá trị 5, ba lô 0/1 dung lượng 6. Nếu bảng 1D trả 10 thì lỗi là gì? **Đáp án:** đã dùng món hai lần, thường do quét dung lượng tăng dần. Kết quả đúng là 5.

**Câu 2.** Với các món `(2,4),(3,5),(4,7)` và dung lượng 6, 0/1 và unbounded trả bao nhiêu? **Đáp án:** 0/1 là 11 (chọn 2 và 4); unbounded là 12 (ba lần loại trọng lượng 2).

**Câu 3.** Vì sao quét giảm giúp bảo toàn `F(i-1,c-w)` ở ba lô 0/1? **Đáp án:** với w>0, `c-w<c`. Khi đang duyệt giảm, mọi chỉ số nhỏ hơn c **chưa bị ghi trong lượt i**, nên vẫn giữ hàng trước.

**Câu 4.** Với dãy `[3,5]`, target 6, subset sum 0/1 là true hay false? **Đáp án:** false; không được lấy số 3 hai lần. Quét tăng dần sẽ tạo false positive.

**Câu 5.** Với lưới 3 hàng và 4 cột, tại sao cách nén một hàng trả 10? **Đáp án:** các hàng giá trị lần lượt `[1,1,1,1]`, `[1,2,3,4]`, `[1,3,6,10]`, ô cuối có 10 cách.

**Câu 6.** Trong LCS, vì sao chỉ dùng `dp[j]` và `dp[j-1]` mà không lưu `diagonal` chưa đủ? **Đáp án:** `dp[j-1]` đã là ô trái **hàng mới**, trong khi nhánh hai ký tự bằng nhau cần **ô chéo của hàng cũ**.

**Câu 7.** Nếu DP hai chiều có trạng thái `F(i,j)` đọc `F(i-2,j)`, có thể dùng một hàng như 0/1 knapsack ngay không? **Đáp án:** không thể kết luận như vậy. Cần giữ đủ các lớp trước hoặc tìm cách chứng minh/thiết kế cập nhật khác mà không mất giá trị cần đọc.

**Câu 8.** Một bài 0/1 knapsack không chỉ yêu cầu giá trị tối ưu, mà còn phải trả tên các món đã chọn. Có thể chỉ giữ mảng `dp[c]` rồi tự nối `parent[c]` không? **Đáp án:** không mặc nhiên đúng. Parent có thể trộn trạng thái từ các lượt khác nhau; cần bảng truy vết hoặc cách quản lý predecessor với lớp/thời điểm hợp lệ.

**Câu 9.** Độ phức tạp của 0/1 knapsack 1D với n món, dung lượng C là gì? **Đáp án:** O(nC) thời gian, O(C) bộ nhớ, thay vì O(nC) bộ nhớ của bản 2D.

**Câu 10.** Tại sao `target=0` trong subset sum có kết quả true, kể cả khi dãy rỗng? **Đáp án:** chọn **không phần tử nào** tạo tổng 0; đây là trạng thái gốc.

**Câu 11.** Nếu lưới không có vật cản nhưng số hàng bằng 0, cách diễn giải phù hợp là gì? **Đáp án:** không có ô bắt đầu/đích, nên chương trình minh họa trả 0; không cấp mảng cột khi biết lưới rỗng.

**Câu 12.** Một bài đếm cách đi lưới cần số lượng chính xác nhưng kết quả vượt `long`. Nén bộ nhớ có sửa được lỗi này không? **Đáp án:** không. Đây là vấn đề **miền giá trị số học**, cần `BigInteger` hoặc một cách biểu diễn chính xác khác; việc nén hàng chỉ giải quyết bộ nhớ.

## 14. Checklist áp dụng vào một bài DP mới

1. Viết rõ **định nghĩa trạng thái**, tham số hàng/lớp và thứ tự xử lý.
2. Ghi lại **mọi phụ thuộc** của `dp[i][j]`: từ hàng trước, cùng hàng, ô chéo, hay nhiều lớp.
3. Nếu nén `dp[i][j]` thành `dp[j]`, kiểm tra **ô nào còn giá trị hàng trước** tại thời điểm đọc.
4. Chọn **hướng quét**: 0/1 thường giảm; dùng lại phần tử/cùng hàng thường tăng — nhưng phải dựa vào công thức cụ thể.
5. Nếu cần cả **ô chéo cũ**, lưu bằng biến tạm trước khi ghi đè (ví dụ LCS).
6. Xử lý **khởi tạo và biên**: dung lượng 0, tập rỗng, lưới rỗng, chuỗi rỗng, trạng thái không thể đạt.
7. Nếu cần **phục dựng nghiệm**, lên kế hoạch bộ nhớ/thời gian riêng cho thông tin lựa chọn.
8. Thử một phản ví dụ rất nhỏ để phát hiện **tái sử dụng sai** một phần tử hoặc đọc nhầm lớp.
9. Đối chiếu bản 1D với bản 2D hoặc brute force trên dữ liệu nhỏ để kiểm tra mọi trạng thái.
10. Phân tích riêng **thời gian O(số trạng thái)** và **bộ nhớ O(số lớp cần giữ × độ rộng hàng)**; không gọi O(C) là hằng số.

**Ghi nhớ:** rút gọn chiều DP không phải chỉ “xóa chỉ số i” khỏi bảng. Mỗi phép đọc phải lấy đúng **phiên bản trạng thái** mà công thức yêu cầu. Chứng minh rằng thứ tự cập nhật không phá giá trị còn cần dùng mới là điều kiện giữ đúng dữ liệu.

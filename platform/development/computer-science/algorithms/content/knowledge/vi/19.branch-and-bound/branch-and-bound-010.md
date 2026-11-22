# Phân biệt nhánh và cận với quay lui kiểm tra tính hợp lệ

**Quay lui kiểm tra tính hợp lệ (backtracking with feasibility pruning)** và **nhánh và cận (branch and bound, B&B)** đều xây một **cây các quyết định** và bỏ qua những nhánh không cần duyệt. Điểm khác biệt cốt lõi nằm ở **lý do được phép bỏ nhánh**:

- **Quay lui kiểm tra tính hợp lệ:** bỏ nhánh khi **phương án đang xây không thể tiếp tục thành một nghiệm hợp lệ**; ví dụ hai quân hậu chung đường chéo, hoặc một tập món vượt sức chứa và không thể bỏ bớt những món đã chọn.
- **Nhánh và cận:** ngoài việc bỏ nhánh **không hợp lệ**, còn bỏ một nhánh **vẫn có thể hoàn thành hợp lệ** nếu một **cận lạc quan đã chứng minh** cho thấy mọi nghiệm trong nhánh ấy đều **không thể tốt hơn nghiệm hoàn chỉnh tốt nhất đang biết**.

Hai cách không hoàn toàn tách biệt: **backtracking là một khung duyệt/hoàn tác lựa chọn**, còn **branch-and-bound là chiến lược cắt nhánh dựa trên cận tối ưu**. Một thuật toán B&B có thể dùng **DFS với chọn–thử–hoàn tác** giống quay lui; khác biệt nằm ở điều kiện cắt nhánh bổ sung và mục tiêu tối ưu.

Bài học thuộc phần **Nhánh và cận** của Computer Science Algorithms. Ta sẽ dùng **N quân hậu** để minh họa cắt theo tính hợp lệ và dùng **ba lô 0/1** để so sánh hai cách giải trên **chính cùng một cây tìm kiếm**. Một chương trình **Java 17+** cung cấp hai solver, thống kê số nút được thăm, cắt nhánh, ví dụ đầu ra có thể kiểm tra và bộ đối chiếu tự động.

## 1. Ba câu hỏi quyết định thuật toán

Khi đứng tại một nút của cây tìm kiếm, hãy hỏi theo thứ tự:

1. **Phần quyết định hiện tại có vi phạm ràng buộc không?** Nếu vi phạm một ràng buộc không thể sửa bằng các quyết định tiếp theo, phải bỏ nhánh ngay. Đây là **cắt theo tính hợp lệ**.
2. **Có thể hoàn thành nhánh này thành nghiệm hợp lệ không?** Nếu biết chắc **không thể**, cũng có thể bỏ nhánh; ví dụ số chỗ còn lại không đủ để hoàn thành một tổ hợp bắt buộc.
3. **Nếu còn hoàn thành được, nghiệm tốt nhất trong nhánh có thể thắng nghiệm đang giữ không?** Nếu có **cận trên** đủ chặt cho bài tối đa hóa hoặc **cận dưới** đủ chặt cho bài tối thiểu hóa, ta có thể bỏ nhánh dù nó không vi phạm ràng buộc.

Một nghiệm hiện tại **hợp lệ** không đồng nghĩa **có thể cải thiện kết quả tốt nhất**. Ngược lại, một nghiệm có điểm số hiện tại thấp **không đồng nghĩa** với nhánh không đáng khám phá: phần còn lại có thể mang lại giá trị rất cao.

### So sánh ngắn

| Tiêu chí | Quay lui kiểm tra hợp lệ | Nhánh và cận |
| --- | --- | --- |
| Mục tiêu phổ biến | Tìm một nghiệm, liệt kê/đếm nghiệm, kiểm tra tồn tại | Tìm nghiệm **tối ưu** (min hoặc max) |
| Nút tìm kiếm | Phương án từng phần | Phương án từng phần kèm giá trị hiện tại và thông tin cận |
| Điều kiện cắt chính | Tiền tố **không thể hoàn thiện hợp lệ** | Tiền tố không hợp lệ **hoặc** không thể vượt nghiệm tốt nhất |
| Cần nghiệm tốt nhất đang biết (incumbent)? | Không cần cho cắt hợp lệ | **Có** trong mô hình B&B tối ưu |
| Cần hàm cận? | Không bắt buộc | **Cần cận đúng hướng và an toàn** |
| Có thể cắt nhánh vẫn hợp lệ? | Không, nếu chỉ dựa trên tính hợp lệ | **Có**, nếu cận chứng minh không cải thiện được |
| DFS/đệ quy? | Thường dùng | Có thể dùng DFS, BFS, best-first, hàng đợi ưu tiên |
| Bảo đảm tối ưu? | Có thể tìm tối ưu nếu duyệt hết các nghiệm và so sánh | Có, nếu cắt bằng cận an toàn và duyệt đúng |
| Rủi ro chính | Kiểm tra thiếu ràng buộc, quên hoàn tác | **Cận không lạc quan**, cập nhật incumbent sai, nhầm hướng bất đẳng thức |

**Điều quan trọng:** chỉ gọi hàm tìm kiếm là `backtrack` hay `branchBound` không quyết định bản chất. Phải xem **trong code nhánh bị loại vì sao**.

## 2. Cây quyết định và tiền tố lời giải

Xét ba lô 0/1 có n món. Mỗi món i có trọng lượng nguyên dương `w[i]`, giá trị nguyên không âm `v[i]`. Sức chứa C nguyên không âm. Mỗi món được **chọn tối đa một lần**. Cần tối đa tổng giá trị, với tổng trọng lượng **không vượt C**; được phép chọn tập rỗng.

Một nhánh ứng với một dãy quyết định:

~~~text
item 0: take or skip
item 1: take or skip
...
item n-1: take or skip
~~~

Trạng thái đang duyệt có thể viết:

`(index, remainingCapacity, currentValue, selectedItems)`

- `index`: món tiếp theo cần quyết định.
- `remainingCapacity`: sức chứa còn lại.
- `currentValue`: tổng giá trị đã lấy.
- `selectedItems`: những món đã chọn ở tiền tố.

Từ nút này có tối đa **hai nhánh**:

1. **Take:** chọn món `index` nếu `w[index] <= remainingCapacity`, rồi cập nhật dung lượng và giá trị.
2. **Skip:** bỏ món `index`, giữ nguyên dung lượng và giá trị.

Nút lá tại `index==n` biểu diễn một tập món hoàn chỉnh. Nếu mọi bước take đều kiểm tra dung lượng, mọi lá đã đến được đều hợp lệ.

**Cùng một cây quyết định, hai cách cắt khác nhau:**

- Bản **quay lui thuần túy** chỉ bỏ nhánh take nào **quá dung lượng**; vẫn duyệt mọi phần mở rộng hợp lệ.
- Bản **nhánh và cận** cũng bỏ take quá dung lượng, **và** có thể loại cả nút cha nếu một cận trên `UB(state)` chứng minh không có hoàn thiện nào đạt điểm tốt hơn incumbent.

Đây là cách so sánh công bằng: cùng bài, cùng thứ tự món, cùng thứ tự thử nhánh, chỉ khác phép cắt theo cận.

## 3. Quay lui kiểm tra tính hợp lệ: ví dụ N quân hậu

Trong **N quân hậu**, cần đặt đúng N quân hậu trên bàn N×N, không hai quân nào tấn công nhau theo hàng, cột và hai đường chéo. Một cách quay lui điển hình đặt **một quân ở mỗi hàng**.

Giả sử đang đặt quân ở hàng `r`, thử cột `c`. Kiểm tra:

~~~text
NOT usedCol[c]
AND NOT usedDiagMain[r-c+N-1]
AND NOT usedDiagAnti[r+c]
~~~

Nếu một trong ba tài nguyên đã bị chiếm, đặt quân vào `(r,c)` sẽ tạo xung đột **ngay trong tiền tố**. Những quân đặt ở các hàng phía dưới không thể xóa xung đột này. Bởi vậy, cắt nhánh là **an toàn do không hợp lệ**, không cần biết bất kỳ nghiệm tối ưu hoặc cận số học nào.

Giả mã:

~~~text
PROCEDURE QUEENS(row)
    IF row == N THEN
        solutions <- solutions + 1
        RETURN
    END IF

    FOR col FROM 0 TO N-1 DO
        IF column/diagonal conflict THEN
            CONTINUE  // Prune: tiền tố không hợp lệ.
        END IF

        MARK(row,col)
        QUEENS(row+1)
        UNMARK(row,col)
    END FOR
END PROCEDURE
~~~

Với N=4 có **2 nghiệm**, N=2 có **0**, N=8 có **92** cấu hình nếu đếm mọi bàn cờ khác tọa độ. Bài toán này thường yêu cầu **đếm hoặc liệt kê mọi nghiệm**, vì vậy nếu đã tìm được một bàn cờ hợp lệ mà cắt những nhánh khác chỉ vì “đã có nghiệm”, kết quả đếm sẽ **sai**.

**Chọn–đi sâu–hoàn tác là backtracking.** Một chương trình B&B dùng DFS cũng có thể có chính các bước này, nhưng thêm một phép kiểm tra **cận tối ưu** trước khi rẽ nhánh.

## 4. Incumbent và cận: thành phần tạo nên nhánh và cận

### Incumbent: nghiệm tốt nhất đã tìm được

**Incumbent** là **giá trị của một nghiệm hoàn chỉnh, hợp lệ** tốt nhất đã biết:

- Với bài **tối đa hóa**, ký hiệu `best`; nó là một **cận dưới cho tối ưu toàn cục** vì đã có ít nhất một nghiệm đạt best.
- Với bài **tối thiểu hóa**, best là **cận trên cho tối ưu toàn cục** vì đã có một phương án khả thi có chi phí best.

Trong ba lô 0/1, **tập rỗng hợp lệ và có giá trị 0**, nên `best=0` là một incumbent an toàn khi mọi giá trị không âm. Khi tìm được một lá có giá trị lớn hơn, cập nhật best.

**Không bao giờ** xem một phương án còn chưa hoàn thiện hoặc đã vi phạm ràng buộc là incumbent. Nếu best được cập nhật bằng một giá trị **không thể đạt**, thuật toán có thể cắt mất mọi lời giải thật sự tối ưu.

### Upper bound: cận trên cho bài tối đa hóa

Với một nút u, `UB(u)` là số thỏa:

`OPT(u) <= UB(u)`

trong đó `OPT(u)` là giá trị cao nhất **có thể đạt bởi một nghiệm hoàn chỉnh hợp lệ nằm trong nhánh u**. Cận trên được phép **lạc quan**, tức lớn hơn giá trị thực sự có thể đạt; nhưng **không được thấp hơn** tối ưu của nhánh.

Nếu `UB(u) <= best` thì **không nghiệm nào trong nhánh có thể cải thiện incumbent**. Ta bỏ toàn bộ nhánh mà vẫn giữ được **giá trị tối ưu cuối cùng**.

~~~text
IF UB(node) <= best THEN
    PRUNE ENTIRE SUBTREE
END IF
~~~

Nếu yêu cầu **liệt kê mọi nghiệm cùng tối ưu**, dấu `<=` không còn phù hợp để xóa nhánh bằng điểm số bằng best: một nhánh có thể chứa **nghiệm khác cũng đạt best**. Khi cần mọi nghiệm đồng tối ưu, phải xét quan hệ `UB < best` hoặc cơ chế đếm/phục dựng bổ sung.

### Lower bound: cận dưới cho bài tối thiểu hóa

Với bài tối thiểu hóa, dùng cận dưới `LB(u)` thỏa:

`LB(u) <= OPT_COST(u)`

trong đó OPT_COST là chi phí thấp nhất có thể đạt từ nhánh u. Nếu `LB(u) >= bestCost`, nhánh không thể cải thiện nghiệm chi phí nhỏ nhất hiện có, nên có thể cắt.

| Mục tiêu | Cận cho nhánh | Điều kiện cắt khi chỉ cần một optimum |
| --- | --- | --- |
| **Maximize value** | Cận **trên** `UB>=optimum of subtree` | `UB<=bestValue` |
| **Minimize cost** | Cận **dưới** `LB<=optimum cost of subtree` | `LB>=bestCost` |

**Đừng đảo dấu.** Dùng một cận **quá thấp** cho bài tối đa hóa có thể giết nhánh chứa nghiệm tối ưu; dùng một cận **quá cao** cho bài tối thiểu hóa cũng sai.

## 5. Các phép cắt hợp lệ không giống phép cắt theo cận

Một số ví dụ:

**Cắt vì vi phạm ràng buộc:** đã chọn món có tổng trọng lượng 8 khi C=7. Vì đã chọn thì không được bỏ món trong cùng nhánh và các bước sau chỉ có thể thêm hoặc không thêm, tổng trọng lượng không thể giảm. Nhánh sai ngay; đây là cắt hợp lệ.

**Cắt vì không thể hoàn tất yêu cầu:** còn hai ô hàng chưa điền mà chỉ còn một cột có thể sử dụng, nên không thể đặt thêm hai quân hậu không cùng cột. Dù một số quân đã đặt không xung đột, nếu có chứng minh không thể hoàn tất, vẫn là **cắt theo tính khả thi**.

**Cắt vì không thể cải thiện giá trị:** đang có incumbent 13. Một nhánh ba lô có tổng giá trị hiện tại 8 và vẫn hoàn toàn hợp lệ, nhưng cận trên an toàn tính được `UB=12`. Vì 12<13, nhánh này có thể hoàn thành thành nghiệm hợp lệ song **không thể thắng nghiệm 13**. Đây là **branch-and-bound**.

**Không được cắt chỉ vì điểm hiện tại thấp:** incumbent 13, nhánh hiện tại có giá trị 5 nhưng vẫn còn món có giá trị 100 và đủ dung lượng; phép cắt dựa trên `currentValue<13` là sai.

## 6. Cận trên an toàn cho ba lô 0/1 bằng thư giãn phân số

Ta cần một cách tính `UB` sao cho chắc chắn **không thấp hơn** giá trị tốt nhất có thể đạt từ mọi lựa chọn 0/1 còn lại.

Cách chặt và nổi tiếng là **fractional knapsack relaxation** (thư giãn thành ba lô phân số):

> Cho phép lấy **một phần** của món, mặc dù bài toán gốc chỉ cho phép chọn nguyên món.

Tập phương án 0/1 là **tập con** của những phương án cho phép lấy một phần món. Vì thế, tối ưu của bài phân số **không thể nhỏ hơn** tối ưu của bài 0/1. Đây chính là cận trên an toàn.

### Thứ tự giá trị trên mỗi đơn vị trọng lượng

Sắp các món theo `value/weight` **giảm dần**. Ở một nút sau khi xử lý các món trước index, ta lấy sức chứa còn lại R và giá trị hiện tại V. Để tạo cận:

1. Xét từng món chưa xử lý theo tỷ số `value/weight` giảm dần.
2. Nếu món vừa sức chứa còn lại, cộng **toàn bộ** giá trị món vào cận và giảm sức chứa.
3. Nếu món quá nặng, cộng **giá trị tỷ lệ** cho phần trọng lượng còn lại rồi dừng.
4. Nếu không còn dung lượng, dừng.

Giả mã:

~~~text
FUNCTION FRACTIONAL_UPPER_BOUND(index, remaining, value)
    bound <- value
    room <- remaining

    FOR j FROM index TO n-1 DO
        IF room == 0 THEN BREAK END IF

        IF weight[j] <= room THEN
            bound <- bound + value[j]
            room <- room - weight[j]
        ELSE
            bound <- bound
                   + value[j] * room / weight[j]
            BREAK
        END IF
    END FOR

    RETURN bound
END FUNCTION
~~~

Đây là tối ưu cho bài phân số khi các tỷ số đã sắp đúng, vì lựa chọn đơn vị trọng lượng có **giá trị cao hơn trước** không thể làm giảm tổng giá trị so với thay bằng đơn vị trọng lượng có tỷ số thấp hơn.

### Tính cận số nguyên để không mắc lỗi làm tròn

Trong ví dụ Java, cả trọng lượng và giá trị đều là `int` không âm hợp lệ (trọng lượng dương). Tổng giá trị lưu bằng `long`. Thay vì dùng `double` rồi so sánh trực tiếp, thuật toán làm tròn **lên** phần giá trị phân số:

`ceil(remaining * item.value / item.weight)`

và cộng bằng `Math.addExact`. Vì tổng giá trị của nghiệm nguyên là một số nguyên, làm tròn lên vẫn là **cận trên**. Làm tròn **xuống** hoặc dùng số thực bị làm tròn thấp hơn giá trị toán học có thể làm cận **quá thấp** và cắt nhầm một nhánh tối ưu.

Ví dụ có các món còn lại đã sắp theo tỷ số:

~~~text
Remaining capacity = 5
Item A: weight=4, value=7
Item B: weight=5, value=8

Take A entirely: bound += 7, room = 1.
Take 1/5 of B:   bound += 8/5 = 1.6.
Exact fractional bound = currentValue + 8.6.
Integer optimistic bound = currentValue + ceil(8.6).
~~~

Nếu cận phân số bằng 8.6 cộng giá trị hiện tại nguyên, cận nguyên làm tròn lên là `currentValue+9`. Việc này có thể kém chặt hơn cận thực, nhưng không làm sai kết quả.

**Lưu ý:** phép chia phân số trong ví dụ được dùng **chỉ để quyết định có cắt nhánh hay không**. Thuật toán vẫn chỉ được chọn **toàn bộ hoặc bỏ nguyên một món**. Không bao giờ cập nhật incumbent bằng nghiệm phân số vì nó có thể không hợp lệ cho ba lô 0/1.

### Một cận đơn giản hơn, nhưng thường yếu

`UB = currentValue + sum(value of all remaining items)`

là một cận trên an toàn khi mọi giá trị không âm: nó **bỏ qua hoàn toàn sức chứa**, giả vờ lấy được tất cả món. Nhưng vì quá lạc quan, cận thường lớn và ít cắt được nhánh. B&B không buộc dùng cận phân số; nó chỉ cần **cận hợp lệ**, và hiệu quả phụ thuộc cận có **chặt** hay không so với chi phí tính cận.

## 7. So sánh cùng một ví dụ ba lô

Xét các món:

| Món (ID gốc) | Trọng lượng | Giá trị | Value/weight |
| ---: | ---: | ---: | ---: |
| 0 | 2 | 5 | 2,50 |
| 1 | 3 | 4 | 1,33 |
| 2 | 4 | 7 | 1,75 |
| 3 | 5 | 8 | 1,60 |

Sức chứa `C=7`. Cả hai thuật toán trong chương trình sắp món theo tỷ số giảm dần, tức thứ tự quyết định:

`[0,2,3,1]`

Cả hai duyệt **nhánh lấy món trước, rồi mới nhánh bỏ món**, nhằm sớm tìm các nghiệm có giá trị tốt.

**Kết quả tối ưu:** lấy món 0 và 3, trọng lượng `2+5=7`, giá trị `5+8=13`. Mỗi món được lấy tối đa một lần.

### Mô hình quay lui thuần

Đối với mỗi món, kiểm tra nhánh **take** có vừa `remainingCapacity` không:

- Nếu vượt, bỏ đúng nhánh take đó vì **không hợp lệ**.
- Nếu vừa, đi sâu.
- Dù đã tìm thấy nghiệm giá trị 13, vẫn duyệt những phần còn lại **nếu không có thêm quy tắc cắt theo cận**.

Một cây đầy đủ không có cắt sẽ có tối đa `2^(n+1)-1` nút, gồm cả nút trong và lá. Với bài này, do cắt ngay các nhánh quá dung lượng, bản quay lui minh họa **thăm 22 nút** và bỏ **5 lượt thử take không hợp lệ**.

### Mô hình nhánh và cận

Sau khi có best, trước khi rẽ nhánh ở một nút, tính `UB` từ các món chưa xử lý (cho phép lấy phân số). Nếu `UB<=best` thì **không cần duyệt hai nhánh con**, kể cả khi một số lựa chọn trong chúng vẫn hợp lệ.

Với cùng thứ tự món và cùng thứ tự take-trước-skip, bản B&B minh họa:

- Thăm **10 nút**.
- Bỏ **3 lượt thử take quá dung lượng**.
- Cắt sớm **2 cây con** vì cận trên không thể thắng best.
- Vẫn trả **13**, chọn các món **[0,3]**.

Các số đếm này đúng cho **thứ tự sắp, thứ tự duyệt, định nghĩa nút và điều kiện cắt cụ thể của chương trình**. Đổi thứ tự nhánh hoặc cách khởi tạo incumbent có thể đổi số nút được thăm, **nhưng không được đổi giá trị tối ưu**.

### Vì sao cắt một nút hợp lệ có thể đúng?

Một tiền tố như “đã chọn món 0, chưa chọn món 2” tự nó có thể hoàn toàn hợp lệ. Dù vậy, nếu cộng thêm cả **điểm tốt nhất theo mô hình phân số** mà vẫn không vượt best đã biết, không có lý do duyệt sâu để tìm giá trị lớn hơn.

Sự khác biệt không nằm ở khả năng **kiểm tra một lựa chọn có hợp lệ hay không**. B&B có thêm khả năng **chứng minh cả phần còn lại của nhánh không có cơ hội cải thiện mục tiêu**.

## 8. Giả mã hai phiên bản trên cùng cây nhị phân

### Chỉ quay lui kiểm tra hợp lệ

~~~text
best <- 0

PROCEDURE BACKTRACK(i, remaining, value)
    IF i == n THEN
        best <- MAX(best, value)
        RETURN
    END IF

    IF weight[i] <= remaining THEN
        BACKTRACK(i+1, remaining-weight[i],
                     value+valueOfItem[i])
    ELSE
        // Nhánh take không hợp lệ: bỏ đúng lựa chọn này.
    END IF

    BACKTRACK(i+1, remaining, value) // Skip item i.
END PROCEDURE
~~~

Thuật toán có thể giải tối ưu vì nó **duyệt toàn bộ các tập món hợp lệ** rồi giữ giá trị lớn nhất. Nhưng không có cận mục tiêu, nên nó không biết bỏ các tập món hợp lệ **chắc chắn kém best** trước khi đi đến lá.

### Thêm điều kiện nhánh và cận

~~~text
best <- 0

PROCEDURE BRANCH_AND_BOUND(i, remaining, value)
    IF i == n THEN
        best <- MAX(best, value) // Nghiệm hoàn chỉnh hợp lệ.
        RETURN
    END IF

    optimistic <- SAFE_UPPER_BOUND(i, remaining, value)
    IF optimistic <= best THEN
        RETURN // Cắt nhánh dù có thể tồn tại nghiệm hợp lệ.
    END IF

    IF weight[i] <= remaining THEN
        BRANCH_AND_BOUND(i+1, remaining-weight[i],
                           value+valueOfItem[i])
    END IF

    BRANCH_AND_BOUND(i+1, remaining, value)
END PROCEDURE
~~~

**Chứng minh bảo toàn tối ưu khi cắt:** best là giá trị **đã đạt bởi một nghiệm hoàn chỉnh**. Vì UB là **cận trên an toàn** cho mọi phần mở rộng của nút u, nếu `UB(u)<=best` thì mọi nghiệm hoàn chỉnh của u có giá trị `<=best`. Vì vậy, bỏ cả nhánh u không thể làm mất một nghiệm có giá trị **lớn hơn best**. Những nhánh không bị cắt vẫn được duyệt theo cùng hai lựa chọn take/skip; khi tìm được nghiệm tốt hơn, best được cập nhật. Kết quả cuối cùng là tối ưu.

**Điều kiện kết thúc:** chỉ số i tăng đúng 1 ở mỗi lời gọi, nên độ sâu không vượt n. Mỗi nút có tối đa hai con, cây hữu hạn; cả hai thuật toán đều kết thúc.

## 9. Java 17+ — chương trình so sánh thực thi

Tệp sau chứa **hai solver** dùng chung cùng mô hình dữ liệu và thứ tự nhánh. Khác biệt duy nhất khi mở rộng tìm kiếm là cờ `useBound`: bản B&B tính và áp dụng cận phân số, còn bản thuần **chỉ cắt lựa chọn quá dung lượng**.

Chương trình cũng có `countNQueens` để minh họa bài chỉ cần **kiểm tra hợp lệ**, `verifyResult` để kiểm tra nghiệm đã chọn, và `crossCheck` so sánh cả hai solver trên 200 đầu vào nhỏ với seed cố định.

Giới hạn dữ liệu: `capacity>=0`, `weights[i]>0`, `values[i]>=0`, trọng lượng và giá trị từng món thuộc `int`. Tỷ số được sắp bằng tích chéo kiểu `long` để không phụ thuộc sai số `double`; hai tích kiểu int dương tối đa vẫn nằm trong `long`. Tổng giá trị và cận dùng `Math.addExact` để **báo tràn** thay vì âm thầm dùng số sai.

Tạo tệp **`BacktrackingVsBranchBoundDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public class BacktrackingVsBranchBoundDemo {
    record Item(int id, int weight, int value) {}

    record Result(long bestValue, List<Integer> items,
                  long visited, long invalidTake,
                  long boundPruned) {}

    private static final class Solver {
        final Item[] items;
        final boolean useBound;
        final boolean[] chosen;
        final boolean[] bestChosen;

        long best = 0L;
        long visited = 0L;
        long invalidTake = 0L;
        long boundPruned = 0L;

        Solver(Item[] items, boolean useBound) {
            this.items = items;
            this.useBound = useBound;
            chosen = new boolean[items.length];
            bestChosen = new boolean[items.length];
        }

        // Cận trên của bài 0/1 bằng thư giãn ba lô phân số.
        // Mảng items đã sắp giảm theo value / weight.
        long upperBound(int index, int room, long value) {
            long upper = value;

            for (int j = index; j < items.length && room > 0; j++) {
                Item item = items[j];
                if (item.weight() <= room) {
                    upper = Math.addExact(upper, item.value());
                    room -= item.weight();
                } else {
                    // Làm tròn LÊN để không đánh giá thấp cận trên.
                    long numerator = (long) room * item.value();
                    long fractionalCeiling =
                            (numerator + item.weight() - 1L)
                            / item.weight();
                    upper = Math.addExact(upper, fractionalCeiling);
                    break;
                }
            }
            return upper;
        }

        void search(int index, int room, long value) {
            visited++;

            if (index == items.length) {
                if (value > best) {
                    best = value;
                    System.arraycopy(chosen, 0, bestChosen, 0,
                                     chosen.length);
                }
                return;
            }

            if (useBound && upperBound(index, room, value) <= best) {
                boundPruned++;
                return;
            }

            Item item = items[index];

            // Nhánh TAKE trước: kiểm tra tính hợp lệ.
            if (item.weight() <= room) {
                chosen[index] = true;
                search(index + 1, room - item.weight(),
                       Math.addExact(value, item.value()));
                chosen[index] = false;
            } else {
                invalidTake++;
            }

            // Nhánh SKIP luôn hợp lệ.
            search(index + 1, room, value);
        }

        Result result() {
            List<Integer> selected = new ArrayList<>();
            for (int i = 0; i < items.length; i++) {
                if (bestChosen[i]) {
                    selected.add(items[i].id());
                }
            }
            Collections.sort(selected);
            return new Result(best, List.copyOf(selected),
                              visited, invalidTake, boundPruned);
        }
    }

    public static Result solve(int[] weights, int[] values,
                               int capacity, boolean useBound) {
        Objects.requireNonNull(weights, "weights");
        Objects.requireNonNull(values, "values");
        if (capacity < 0 || weights.length != values.length) {
            throw new IllegalArgumentException("Invalid dimensions");
        }

        Item[] items = new Item[weights.length];
        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException(
                        "Weight positive, value nonnegative");
            }
            items[i] = new Item(i, weights[i], values[i]);
        }

        // Tỷ số giảm dần, so sánh tích chéo chính xác.
        Arrays.sort(items, (a, b) -> {
            long lhs = (long) a.value() * b.weight();
            long rhs = (long) b.value() * a.weight();
            int cmp = Long.compare(rhs, lhs);
            return cmp != 0 ? cmp : Integer.compare(a.id(), b.id());
        });

        Solver solver = new Solver(items, useBound);
        solver.search(0, capacity, 0L);
        return solver.result();
    }

    private static void verifyResult(Result result,
                                     int[] weights, int[] values,
                                     int capacity) {
        boolean[] seen = new boolean[weights.length];
        long usedWeight = 0L;
        long totalValue = 0L;

        for (int id : result.items()) {
            if (id < 0 || id >= weights.length || seen[id]) {
                throw new AssertionError("Duplicate/invalid item");
            }
            seen[id] = true;
            usedWeight += weights[id];
            totalValue = Math.addExact(totalValue, values[id]);
        }

        if (usedWeight > capacity ||
                totalValue != result.bestValue()) {
            throw new AssertionError("Invalid solution");
        }
    }

    private static void show(String label, Result result) {
        System.out.println(label + "=" + result.bestValue()
                + " items=" + result.items()
                + " visited=" + result.visited()
                + " invalidTake=" + result.invalidTake()
                + " boundPruned=" + result.boundPruned());
    }

    private static long queensDfs(int row, int n,
                                  boolean[] cols,
                                  boolean[] down, boolean[] up) {
        if (row == n) {
            return 1L;
        }

        long ways = 0L;
        for (int c = 0; c < n; c++) {
            int d1 = row - c + n - 1;
            int d2 = row + c;

            if (cols[c] || down[d1] || up[d2]) {
                continue; // Chỉ cắt vì vị trí KHÔNG HỢP LỆ.
            }

            cols[c] = down[d1] = up[d2] = true;
            ways += queensDfs(row + 1, n, cols, down, up);
            cols[c] = down[d1] = up[d2] = false;
        }
        return ways;
    }

    public static long countNQueens(int n) {
        if (n < 1 || n > 12) {
            throw new IllegalArgumentException("Use 1 <= n <= 12");
        }
        return queensDfs(0, n, new boolean[n],
                new boolean[2 * n - 1],
                new boolean[2 * n - 1]);
    }

    private static void crossCheck() {
        Random random = new Random(2026L);

        for (int test = 0; test < 200; test++) {
            int n = random.nextInt(9);
            int capacity = random.nextInt(16);
            int[] weights = new int[n];
            int[] values = new int[n];

            for (int i = 0; i < n; i++) {
                weights[i] = 1 + random.nextInt(8);
                values[i] = random.nextInt(16);
            }

            Result plain = solve(weights, values, capacity, false);
            Result bounded = solve(weights, values, capacity, true);

            verifyResult(plain, weights, values, capacity);
            verifyResult(bounded, weights, values, capacity);

            if (plain.bestValue() != bounded.bestValue()) {
                throw new AssertionError("Wrong bound at test " + test);
            }
            if (bounded.visited() > plain.visited()) {
                throw new AssertionError("Unexpected node count");
            }
        }

        System.out.println("crossCheck=PASS (200 cases)");
    }

    public static void main(String[] args) {
        int[] weights = {2, 3, 4, 5};
        int[] values = {5, 4, 7, 8};

        Result plain = solve(weights, values, 7, false);
        Result bounded = solve(weights, values, 7, true);
        verifyResult(plain, weights, values, 7);
        verifyResult(bounded, weights, values, 7);

        show("plain", plain);
        show("bounded", bounded);
        System.out.println("sameBest=" +
                (plain.bestValue() == bounded.bestValue()));

        show("tie", solve(new int[]{2, 2},
                new int[]{5, 5}, 2, true));
        show("zeroCapacity", solve(new int[]{2, 3},
                new int[]{5, 4}, 0, true));
        show("empty", solve(new int[0], new int[0], 4, true));

        System.out.println("queens2=" + countNQueens(2));
        System.out.println("queens4=" + countNQueens(4));
        System.out.println("queens8=" + countNQueens(8));

        crossCheck();
    }
}
~~~

Biên dịch/chạy với **JDK 17 trở lên**:

~~~bash
javac BacktrackingVsBranchBoundDemo.java
java BacktrackingVsBranchBoundDemo
~~~

**Đầu ra xác định:**

~~~text
plain=13 items=[0, 3] visited=22 invalidTake=5 boundPruned=0
bounded=13 items=[0, 3] visited=10 invalidTake=3 boundPruned=2
sameBest=true
tie=5 items=[0] visited=4 invalidTake=1 boundPruned=1
zeroCapacity=0 items=[] visited=1 invalidTake=0 boundPruned=1
empty=0 items=[] visited=1 invalidTake=0 boundPruned=0
queens2=0
queens4=2
queens8=92
crossCheck=PASS (200 cases)
~~~

### Cách diễn giải bộ đếm

- `visited`: số lần gọi `search`, **bao gồm** nút lá và nút bị cận cắt ngay khi vừa vào. Nút không sinh ra vì take quá dung lượng **không được tính là visited**.
- `invalidTake`: số lần thử nhánh take bị bỏ vì món không vừa `room`. Đây là **cắt theo tính hợp lệ**, không phải cắt theo cận.
- `boundPruned`: số lần dừng **cả một cây con** tại nút đã thăm vì `UB<=best`; chỉ xuất hiện khi `useBound=true`.
- `plain` và `bounded` đều đạt giá trị 13 và cùng tập món [0,3]; sự khác biệt nằm ở **số nút đã khám phá**.
- `tie`: hai món (2,5) giống nhau, sức chứa 2. Chương trình trả một nghiệm tối ưu bất kỳ và ưu tiên nhánh take trước, nên chọn món gốc có chỉ số 0.
- `zeroCapacity`: tập rỗng có giá trị 0, do đó `best=0` đã là incumbent hợp lệ. Cận ở gốc cũng bằng 0 nên B&B có thể cắt ngay, không cần duyệt tới lá.
- `empty`: không có món, gốc đồng thời là lá, trả 0.
- `queens2/4/8`: bài **quay lui kiểm tra hợp lệ** đếm lần lượt 0,2,92 nghiệm, không có incumbent/cận tối ưu.
- `crossCheck`: với 200 bộ dữ liệu nhỏ có seed cố định, chương trình kiểm tra hai cách cho giá trị tối ưu giống nhau và nghiệm trả về không trùng món hay vượt dung lượng; lỗi sẽ ném `AssertionError` thay vì in PASS.

**Kết quả số nút phụ thuộc thứ tự duyệt.** Chương trình cố định sắp món theo tỷ số giảm dần, rồi thử take trước. Nếu thay thứ tự, có thể tìm incumbent tốt hơn sớm hoặc muộn, khiến `visited` và `boundPruned` thay đổi. Giá trị tối ưu **không được thay đổi** nếu thuật toán và cận vẫn đúng.

## 10. Vì sao cận phân số là an toàn trong chương trình?

**Bước 1:** ở một nút, những món chưa xét là các món từ `index` đến n-1 trong danh sách đã sắp theo tỷ số `value/weight` giảm dần.

**Bước 2:** bài 0/1 bắt buộc chỉ chọn `0` hoặc `1` phần của mỗi món. Bài phân số nới ràng buộc thành `0<=x_i<=1`, nên mọi lựa chọn 0/1 hợp lệ cũng là một lựa chọn phân số hợp lệ.

**Bước 3:** đối với bài phân số có một giới hạn trọng lượng và các giá trị không âm, lấy các món theo tỷ số giảm dần cho đến khi hết dung lượng (món cuối có thể chỉ lấy một phần) đạt tối ưu phân số. Do đó kết quả này **lớn hơn hoặc bằng** mọi giá trị 0/1 có thể đạt từ nút.

**Bước 4:** chương trình làm tròn phần giá trị phân số cuối **lên** số nguyên. Điều này chỉ **tăng hoặc giữ nguyên** cận, nên không gây cắt nhầm do làm tròn xuống.

**Bước 5:** chỉ cắt khi cận trên này `<=best`, trong khi best xuất phát từ tập rỗng hợp lệ và chỉ được tăng tại một **lá hoàn chỉnh**. Vì thế mọi nghiệm trong nhánh bị cắt đều **không cải thiện được** best hiện có.

Có thể dùng một cận rất rộng (chẳng hạn cộng toàn bộ giá trị còn lại) mà vẫn đúng, nhưng ít cắt hơn. Ngược lại, một “cận” quá thấp thường cắt nhiều hơn nhưng **không còn thuật toán tối ưu chính xác**.

### Phản ví dụ cận sai

Có `best=10` từ một nghiệm hợp lệ. Một nút còn dung lượng 4 và **hai món** cùng `(weight=2,value=6)`. Hai món có thể chọn cùng nhau để được 12. Nếu ai đó tính “cận trên” bằng cách chỉ cộng **giá trị của món lớn nhất còn lại**:

~~~text
wrongBound = currentValue + maxRemainingSingleItemValue
           = 0 + 6
           = 6
~~~

rồi cắt vì 6<=10, thuật toán đã bỏ mất nhánh có nghiệm **12**. Giá trị 6 **không phải cận trên**, vì đã quên khả năng chọn **nhiều món** trong phần còn lại.

Bài học: một hàm có tên `upperBound` nhưng **không được chứng minh luôn >= tối ưu của nhánh** thì không được dùng để loại nhánh.

## 11. Độ phức tạp và bộ nhớ

### Quay lui ba lô 0/1 thuần

Có n quyết định nhị phân. Trong trường hợp xấu (sức chứa đủ lớn), cây đầy đủ có `2^(n+1)-1` nút. Mỗi nút thực hiện thao tác O(1), nên thời gian **O(2^n)**, chưa tính sắp thứ tự món và thao tác xuất nghiệm. Trong chương trình hai solver cùng sắp món O(n log n) để so sánh công bằng; việc sắp không cần thiết cho tính đúng của quay lui thuần.

### Nhánh và cận ba lô 0/1

B&B có thể cắt nhiều cây con, nhưng **không bảo đảm luôn cắt được nhiều**. Ở mỗi nút chưa bị cắt, nó tính cận phân số bằng cách quét tối đa O(n) món còn lại; vì vậy chặn trên đơn giản là:

- **O(n log n)** để sắp món.
- **O(n·2^n)** cho tìm kiếm trong trường hợp xấu, do có thể tính cận O(n) ở O(2^n) nút.

Trong thực tế, nếu cận chặt và tìm incumbent tốt sớm, số nút duyệt có thể giảm rất mạnh. Tuy nhiên, việc tính cận có **chi phí riêng**, nên một bản B&B không phải lúc nào cũng chạy nhanh hơn một bản backtracking đơn giản trên dữ liệu nhỏ hoặc dữ liệu ít nhánh có thể cắt.

### Bộ nhớ

Cả hai solver DFS trong chương trình đều cần:

- Mảng món đã sắp: O(n).
- Hai mảng Boolean `chosen`, `bestChosen`: O(n).
- Ngăn xếp đệ quy độ sâu tối đa n: O(n).

Tổng bộ nhớ phụ là **O(n)** (không tính dữ liệu đầu vào/đầu ra khác). Một bản B&B dùng **priority queue** cho chiến lược best-first có thể giữ nhiều nút chưa mở rộng, thậm chí cấp số mũ; không được mặc định mọi cách tổ chức B&B đều chỉ dùng O(n).

### Trường hợp mục tiêu và cận không giúp ích

Nếu best còn rất thấp hoặc cận quá lạc quan, phép so sánh `UB<=best` hiếm khi đúng. B&B vẫn cần duyệt gần như toàn bộ cây, đồng thời tốn thời gian tính cận. Do đó nên xem **tỷ lệ nhánh cắt**, **chi phí tính bound**, **thời gian thực tế** và **bộ nhớ** trên bộ dữ liệu của bài, thay vì kết luận B&B luôn tốt hơn.

## 12. Cách cải thiện B&B mà vẫn giữ tính đúng

### 12.1. Tìm incumbent tốt sớm

Có thể xây một nghiệm hợp lệ ban đầu bằng **tham lam**: duyệt món theo tỷ số rồi chọn nguyên món nào vừa sức chứa. Dù tham lam không luôn tối ưu, tập món nó chọn là **nghiệm hợp lệ**, nên tổng giá trị là một incumbent an toàn. Nếu incumbent ban đầu cao, nhiều nhánh với cận thấp sẽ bị loại sớm hơn.

Điều kiện bắt buộc: **nghiệm tham lam phải thật sự hợp lệ**. Không thể đưa giá trị bài **phân số** làm incumbent, vì có thể không tồn tại tập món 0/1 nào đạt giá trị đó.

### 12.2. Chọn thứ tự nhánh tốt

Trong bài tối đa giá trị, thử **take trước skip** với món có tỷ số cao có thể đưa đến nghiệm tốt sớm, nhưng không được coi đó là bảo đảm toàn cục. Thứ tự nhánh có thể thay đổi số nút và tốc độ; nó **không được làm thay đổi các lựa chọn hợp lệ** mà thuật toán phải xét nếu không bị cận an toàn loại.

### 12.3. Cận chặt nhưng tính được nhanh

Một cận càng gần tối ưu thật của cây con, thường càng cắt tốt; nhưng có thể tốn nhiều thời gian. Cần đánh đổi:

- Cận rất rẻ nhưng rộng: cộng tất cả giá trị món còn lại.
- Cận chặt hơn: ba lô phân số.
- Cận phức tạp hơn: kết hợp những ràng buộc bổ sung hoặc lời giải thư giãn mạnh hơn khi bài có nhiều điều kiện.

Không được dùng một cận mạnh nhưng **không chứng minh đúng**. Một cận sai làm thuật toán trả đáp án sai có vẻ rất nhanh.

### 12.4. DFS, BFS và best-first

Nhánh và cận không bắt buộc dùng đệ quy DFS. Có thể dùng:

- **DFS:** ít bộ nhớ frontier hơn, dễ lưu và hoàn tác trạng thái, có thể sớm tìm một nghiệm hoàn chỉnh.
- **BFS:** mở rộng theo độ sâu, cần hàng đợi các nút chưa xử lý.
- **Best-first:** ưu tiên nút có cận hấp dẫn nhất, thường dùng hàng đợi ưu tiên; có thể cải thiện tốc độ tìm optimum trong một số bài nhưng tốn bộ nhớ.

Điều kiện cốt lõi vẫn là **cận phải an toàn**, incumbent phải **khả thi**, và không bỏ sót các phần mở rộng có thể thắng incumbent.

## 13. Quan hệ với các kỹ thuật khác

### Backtracking có thể giải bài tối ưu

Một chương trình **không dùng bound** nhưng duyệt hết các nghiệm hợp lệ rồi chọn giá trị lớn nhất vẫn giải đúng bài tối ưu. Vì vậy, phát biểu “quay lui không thể giải tối ưu” là **sai**. Đúng hơn: quay lui chỉ kiểm tra hợp lệ **không có phép cắt dựa vào khả năng cải thiện mục tiêu**, nên có thể làm nhiều việc hơn.

### Branch-and-bound không phải dynamic programming

**Quy hoạch động** thường gộp các trạng thái tương đương thành một bài toán con và tái sử dụng kết quả. **Nhánh và cận** thường cắt nhánh dựa trên cận tối ưu và incumbent. Hai cơ chế khác nhau, có thể **kết hợp** nếu trạng thái và điều kiện trội đủ mạnh.

Ví dụ, DP 0/1 knapsack dùng mảng theo dung lượng có độ phức tạp O(nC) thời gian, O(C) bộ nhớ với trọng lượng nguyên không âm/đặc tả thích hợp. Với C nhỏ, DP thường đơn giản và ổn định hơn DFS B&B. Với C cực lớn mà một cận mạnh cắt được nhiều nhánh, B&B có thể phù hợp hơn.

### Branch-and-bound khác beam search

**Beam search** chỉ giữ một số K nút “hứa hẹn” theo heuristic. Nếu bỏ nút chỉ vì vượt K, **không có bảo đảm tối ưu** trừ khi có chứng minh bổ sung. B&B loại nút khi một **bất đẳng thức hợp lệ** chứng minh nó không thể thắng best; số nút có thể giữ lại không bị giới hạn tùy tiện.

### Branch-and-bound và cắt theo ràng buộc kết hợp

Trong nhiều bài lập lịch, TSP hoặc phân công, một nút có thể bị loại vì:

- Nó đã **không hợp lệ** theo ràng buộc.
- Nó còn hợp lệ, nhưng **lower bound của chi phí** không thể thấp hơn chi phí nghiệm tốt nhất.
- Một trạng thái khác **trội** nó nếu có quan hệ trội đã chứng minh.

Đây là các lý do cắt khác nhau. Có thể kết hợp chúng, nhưng mỗi lý do cần **điều kiện đúng riêng**.

## 14. Những sai lầm điển hình

1. **Gọi mọi thuật toán đệ quy thử và xóa là B&B.** Chưa có cận mục tiêu và incumbent thì chỉ là backtracking/DFS theo điều kiện đang dùng.
2. **Cho rằng B&B luôn có priority queue.** DFS B&B cũng đúng.
3. **Tưởng backtracking không thể tìm tối ưu.** Nó có thể duyệt mọi nghiệm rồi lấy best, chỉ thường ít cắt hơn.
4. **Cắt vì giá trị hiện tại thấp hơn best**, dù còn những món lợi cao phía sau.
5. **Dùng một đại lượng không phải upper bound/lower bound an toàn**, dẫn đến loại cả nhánh có optimum.
6. **Dùng dấu sai chiều:** maximize dùng cận trên, minimize dùng cận dưới.
7. **Đặt incumbent bằng giá trị của nghiệm chưa hoàn tất** hoặc nghiệm vi phạm ràng buộc.
8. **Đặt incumbent bằng nghiệm phân số của bài 0/1.** Giá trị phân số chỉ nên làm upper bound.
9. **Dùng số thực có sai số làm tròn xuống** mà không bảo đảm UB không thấp hơn tối ưu thật.
10. **Cắt `UB<=best` khi phải liệt kê mọi nghiệm đồng tối ưu.** Có thể xóa các nghiệm khác cùng giá trị.
11. **Đếm một tiền tố chưa hoàn tất là nghiệm** trong bài N quân hậu hoặc bài tổ hợp.
12. **Quên hoàn tác sau đệ quy**, gây nhiễu các nhánh anh em.
13. **Cho phép take món quá sức chứa**, rồi cập nhật best bằng nghiệm không hợp lệ.
14. **Thử cùng món nhiều lần trong bài 0/1**, do không tăng index đúng cách.
15. **Cho rằng giá trị UB nhất thiết đạt được.** Nó có thể đến từ việc cho phép lấy phân số, nên không khả thi trong bài gốc.
16. **Nhầm số nút được thăm với số nhánh bị cắt.** Một nhánh take không được sinh không phải một nút visited; cần định nghĩa bộ đếm.
17. **Nhầm giảm số nút với giảm thời gian thực tế.** Tính cận có chi phí.
18. **Kết luận thuật toán luôn đa thức vì một ví dụ cắt rất nhiều nhánh.** Trường hợp xấu vẫn có thể cấp số mũ.
19. **Không xét ảnh hưởng thứ tự nhánh**, rồi so số nút hai phiên bản có thứ tự xử lý khác nhau và gọi đó là so sánh công bằng.
20. **Giả sử mọi bài quay lui cần bound** dù đề chỉ cần đếm toàn bộ nghiệm và không có tiêu chí tối ưu.
21. **Nhầm cắt theo khả thi với cắt theo chất lượng:** một nhánh còn hợp lệ vẫn có thể bị B&B cắt.
22. **Không thử trường hợp số món bằng 0 hoặc dung lượng 0**, khiến incumbent không được khởi tạo đúng.

## 15. Bài tập tự luyện có lời giải

**Câu 1.** N quân hậu đang có hai quân chung đường chéo. Cắt nhánh vì lý do gì? **Đáp án:** vi phạm tính hợp lệ không thể sửa bằng cách đặt thêm quân; đó là pruning của backtracking.

**Câu 2.** Bài tối đa có best=20, một nhánh vẫn khả thi nhưng có UB=17. Có thể cắt không? **Đáp án:** có, nếu 17 là **cận trên đúng** của mọi hoàn thiện trong nhánh, vì không thể cải thiện 20.

**Câu 3.** Bài tối thiểu chi phí có incumbent=50 và cận dưới LB=55. Có thể cắt? **Đáp án:** có, nếu LB đúng; mọi nghiệm trong nhánh có chi phí ít nhất 55 nên không thể thắng 50.

**Câu 4.** Với bài tối đa, giá trị hiện tại là 5, best=13. Có thể cắt ngay không? **Đáp án:** không. Một món còn lại có thể mang giá trị 100; phải biết cận trên của các phần mở rộng.

**Câu 5.** Vì sao cho phép lấy một phần món tạo upper bound cho ba lô 0/1? **Đáp án:** thư giãn làm tập phương án rộng hơn; tối ưu của tập rộng không nhỏ hơn tối ưu của tập 0/1.

**Câu 6.** C=7 và món (2,5),(3,4),(4,7),(5,8). Tối ưu 0/1 bằng bao nhiêu? **Đáp án:** 13, chọn món 0 và 3, dùng trọng lượng 7.

**Câu 7.** Với cùng ví dụ, bản plain và B&B mẫu thăm bao nhiêu nút? **Đáp án:** plain 22, B&B 10 với thứ tự món và take-trước-skip của chương trình. Đây không phải số nút chung cho mọi cài đặt.

**Câu 8.** N quân hậu N=4 có mấy cấu hình nếu phân biệt ảnh phản chiếu? **Đáp án:** 2.

**Câu 9.** Nếu chỉ cần đếm tất cả nghiệm N quân hậu, có thể cắt các nhánh còn lại sau khi tìm được nghiệm đầu không? **Đáp án:** không. Làm vậy chỉ phù hợp với bài **tìm một nghiệm**, không phù hợp với đếm mọi nghiệm.

**Câu 10.** Hai món còn lại đều nặng 2, giá trị 6; còn dung lượng 4 và current=0. Cận “giá trị của một món lớn nhất” bằng 6 có đúng không? **Đáp án:** không; có thể lấy cả hai, giá trị 12. Cận như vậy đánh giá thấp và có thể cắt sai.

**Câu 11.** Tại sao làm tròn `ceil` phần phân số trong cận trên là an toàn cho giá trị nguyên? **Đáp án:** làm tròn lên không thể giảm giá trị cận; do đó nó vẫn ≥ optimum 0/1.

**Câu 12.** Một nhánh có `UB==best` và đề chỉ yêu cầu **giá trị tối ưu**. Có thể cắt? **Đáp án:** có, vì nhánh không thể tạo giá trị **lớn hơn** best.

**Câu 13.** Nếu đề yêu cầu **liệt kê mọi nghiệm tối ưu**, có thể cắt luôn ở `UB==best` không? **Đáp án:** không, vì nhánh có thể chứa nghiệm khác đồng giá trị với incumbent.

**Câu 14.** Mọi giá trị món đều 0. B&B có thể cắt ngay từ gốc không? **Đáp án:** có, vì tập rỗng là nghiệm hợp lệ giá trị 0 và upper bound ở gốc cũng 0.

**Câu 15.** Nếu dùng heuristic giữ 10 nhánh tốt nhất mà không chứng minh cận, có còn bảo đảm tối ưu không? **Đáp án:** không. Đó là cắt tỉa gần đúng, không phải B&B chính xác.

**Câu 16.** Vì sao số nút B&B có thể thay đổi khi đảo thứ tự take/skip? **Đáp án:** thứ tự ảnh hưởng thời điểm tìm được incumbent mạnh; incumbent càng mạnh sớm, càng nhiều cận không thể vượt nó.

**Câu 17.** Nếu bài toán ba lô có thể đạt đúng tối ưu dù không dùng B&B, tại sao còn cần B&B? **Đáp án:** để giảm số nhánh khám phá nhờ cận an toàn khi cây tìm kiếm lớn và cận đủ chặt.

**Câu 18.** Backtracking và branch-and-bound có thể dùng cùng một hàm DFS không? **Đáp án:** có. Một hàm DFS B&B chỉ bổ sung kiểm tra cận so với DFS quay lui, vẫn cần chọn/đi sâu/hoàn tác.

## 16. Checklist chọn cách cắt nhánh

1. **Bài hỏi một nghiệm, đếm mọi nghiệm hay nghiệm tối ưu?** Không áp dụng cắt theo best khi cần giữ mọi nghiệm mà chưa xét yêu cầu đếm.
2. **Trạng thái đã đủ mô tả phần việc còn lại chưa?** Index, vị trí, tài nguyên, quyết định đã chọn.
3. **Điều kiện nào là không hợp lệ không thể sửa?** Từ đó đặt cắt khả thi.
4. **Nếu tối ưu, incumbent có là nghiệm hoàn chỉnh và khả thi không?** Không dùng điểm của nghiệm giả.
5. **Tối đa hay tối thiểu?** Tối đa dùng upper bound, tối thiểu dùng lower bound.
6. **Cận được chứng minh đúng cho mọi hoàn thiện của nhánh chưa?** Không được chỉ ước lượng lạc quan theo cảm giác.
7. **Có xử lý sai số số học, tràn số hoặc phép làm tròn không?** Tránh cận thấp hơn optimum thật.
8. **Dấu cắt có phù hợp đầu ra không?** `<=` khi chỉ cần một optimum, nhưng các nghiệm đồng tối ưu cần lưu/đếm.
9. **Thứ tự nhánh có ưu tiên tìm nghiệm tốt sớm không?** Đây là tối ưu hiệu năng, không thay tính đúng.
10. **Nếu dùng DFS có hoàn tác chính xác không?** Không để một nhánh thay đổi lựa chọn của nhánh khác.
11. **Đã so sánh với backtracking/DP tham chiếu trên dữ liệu nhỏ chưa?** Kiểm tra cả nghiệm và giá trị.
12. **Đã phân tích trường hợp xấu chưa?** B&B vẫn có thể mất thời gian cấp số mũ.
13. **Đã đo đúng visited, invalidTake và boundPruned chưa?** Những số này đo các hiện tượng khác nhau.

**Ghi nhớ:** cắt **vì không hợp lệ** chứng minh một phần lời giải **không thể trở thành nghiệm**; cắt **vì nhánh và cận** chứng minh một phần lời giải **không thể trở thành nghiệm tốt hơn nghiệm đã có**. Cả hai đều cần lập luận đúng, nhưng chỉ loại thứ hai đòi hỏi **incumbent và cận tối ưu an toàn**.

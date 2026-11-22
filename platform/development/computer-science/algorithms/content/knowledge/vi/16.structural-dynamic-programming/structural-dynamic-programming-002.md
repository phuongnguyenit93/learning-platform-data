# Quy hoạch động trên cây với trạng thái ở gốc cây con

**Quy hoạch động trên cây (tree dynamic programming, tree DP)** là cách giải bài toán trên cấu trúc cây bằng cách xác định **trạng thái tại mỗi đỉnh gốc của một cây con**, sau đó tổng hợp kết quả từ các cây con của các đỉnh kề bên. Thay vì duyệt mọi tập hợp đỉnh hoặc mọi phương án độc lập, thuật toán tận dụng việc **bỏ một cạnh nối đỉnh với cha sẽ tách cây thành những nhánh không giao nhau**.

Bài toán trung tâm của bài học là **tập đỉnh độc lập có tổng trọng số lớn nhất trên cây (maximum-weight independent set on a tree)**: chọn một tập đỉnh sao cho **không có hai đỉnh được chọn nối trực tiếp bằng cạnh**, và tổng trọng số lớn nhất. Tại mỗi đỉnh `u`, ta lưu hai trạng thái: **chọn u** và **không chọn u**. Từ hai giá trị này, ta suy ra đáp án của cả cây trong **O(n)** thời gian.

Bài học cũng trình bày **phủ đỉnh tối thiểu (minimum vertex cover)** để thấy cách thay đổi điều kiện chọn, hướng dẫn dựng cây có gốc, duyệt hậu thứ tự, chứng minh đúng, phục dựng tập đỉnh, xử lý trọng số âm, rừng cây, sai lầm thường gặp và chương trình Java 17+ tự chạy. Các phần mở rộng giúp nhận biết khi nào hai trạng thái là đủ và khi nào phải tăng số chiều trạng thái.

## 1. Từ cây vô hướng đến cây có gốc

**Cây vô hướng** có `n` đỉnh là một đồ thị **liên thông và không có chu trình**. Với `n>0`, cây có đúng `n-1` cạnh. Giữa hai đỉnh bất kỳ tồn tại đúng **một đường đi đơn**. Những tính chất này là lý do tree DP hoạt động hiệu quả: sau khi chọn một đỉnh làm gốc, mỗi đỉnh khác gốc có đúng một cha.

Chọn một đỉnh `root`, thường là `0`, để **định hướng quan hệ cha–con**:

- `parent[u]`: cha của `u`; riêng gốc không có cha.
- `children(u)`: các đỉnh kề `u` trừ cha của nó.
- `subtree(u)`: tập các đỉnh gồm `u` và toàn bộ hậu duệ của nó.
- **Lá (leaf):** đỉnh không có con trong cây đã chọn gốc.
- **Hậu thứ tự (postorder):** xử lý con trước cha, bảo đảm trạng thái con đã được tính khi tính cha.

Ví dụ cây có 7 đỉnh:

```text
                0(4)
              /      \
           1(2)      2(3)
          /    \     /   \
       3(5)  4(1)  5(6) 6(2)
```

Số trong ngoặc là **trọng số**. Các cạnh là `(0,1),(0,2),(1,3),(1,4),(2,5),(2,6)`.

Khi đặt gốc ở 0, `subtree(1)={1,3,4}`, `subtree(2)={2,5,6}`. Hai cây con này **không giao nhau**, và **không có cạnh** nối một đỉnh bất kỳ của cây con 1 với một đỉnh bất kỳ của cây con 2. Nếu có cạnh như thế, kết hợp với các đường đi qua 0 sẽ tạo chu trình, trái với định nghĩa cây.

**Chọn gốc không làm thay đổi bài toán vô hướng.** Ta chỉ dùng gốc để thuận tiện định nghĩa và tính DP. Giá trị tối ưu của toàn cây là như nhau dù đặt gốc ở đỉnh nào; tuy nhiên, mảng trạng thái ở từng cây con và tập nghiệm được phục dựng khi có nhiều đáp án tối ưu có thể phụ thuộc cách đặt gốc/phá hòa.

### Vì sao không duyệt mọi hàng xóm như con?

Danh sách kề của đồ thị vô hướng chứa cạnh theo **hai chiều**. Khi đang ở đỉnh `u`, hàng xóm `parent[u]` **không thuộc** `children(u)`. Nếu bỏ qua điều này rồi đệ quy mọi đỉnh kề, thuật toán có thể quay lại cha và lặp vô hạn (`0→1→0→...`).

Trong triển khai, phải phân biệt `v == parent[u]` với `v` là con thật sự của `u`. Đồng thời, dữ liệu đầu vào phải là **cây hợp lệ**; áp dụng cùng công thức cho đồ thị có chu trình có thể tính sai vì các nhánh không còn độc lập.

## 2. Mô hình bài toán tập đỉnh độc lập lớn nhất

Cho mỗi đỉnh `u` một trọng số `w[u]`, có thể là số nguyên âm, 0 hoặc dương. Cần tìm tập `S` sao cho:

1. Nếu `(u,v)` là một cạnh, **không được** có cả `u∈S` và `v∈S`.
2. Tối đa hóa `sum(w[u])` với `u∈S`.

Trong bài này, **được phép chọn tập rỗng** với tổng bằng **0**. Điều này rất quan trọng nếu mọi trọng số đều âm: chọn không đỉnh nào sẽ tốt hơn lấy một đỉnh có trọng số âm. Nếu đề bài yêu cầu **phải chọn ít nhất một đỉnh**, cần bổ sung trạng thái/ràng buộc riêng; không dùng nguyên xi công thức rồi mặc nhiên trả 0.

**Tập độc lập** không có nghĩa các đỉnh được chọn không được nằm chung một cây con. Điều kiện cấm là **hai đỉnh kề trực tiếp**, không phải mọi cặp đỉnh có đường đi nối nhau. Trong ví dụ cây trên, ta có thể chọn đồng thời gốc 0 và các cháu 3,4,5,6, bởi không có cạnh trực tiếp giữa 0 và một cháu.

### Vì sao thử mọi tập con không tốt?

Có `2^n` tập con của `n` đỉnh. Duyệt tất cả tập rồi kiểm tra cạnh có thể giải cây nhỏ nhưng trở nên không thực tế khi `n` lớn. Tree DP rút gọn thông tin về phần cây con thành **hai giá trị** đại diện cho hai trạng thái có ảnh hưởng đến cha: đỉnh gốc cây con **được chọn** hay **không được chọn**.

Không cần ghi lại cách chọn toàn bộ từng cây con trong các trạng thái DP; khi cần **phục dựng**, có thể dựa trên mảng trạng thái đã tính và điều kiện ở cha để đi từ gốc xuống.

## 3. Hai trạng thái tại gốc mỗi cây con

Với đỉnh `u`, định nghĩa:

- **`take[u]`**: tổng trọng số lớn nhất của một tập độc lập **nằm hoàn toàn trong subtree(u)**, với điều kiện **bắt buộc chọn u**.
- **`skip[u]`**: tổng trọng số lớn nhất của một tập độc lập **nằm trong subtree(u)**, với điều kiện **không chọn u**.

Cả hai là các kết quả **có điều kiện**. Chúng không phải là hai đáp án độc lập cho toàn cây. Sau khi xử lý mọi đỉnh, đáp án là:

`answer = max(take[root], skip[root])`.

### Trường hợp chọn u

Nếu đã chọn u, **không được chọn bất kỳ con trực tiếp v nào**, vì `(u,v)` là cạnh. Tuy nhiên, trong cây con của v vẫn có thể chọn **cháu** hoặc các hậu duệ không kề trực tiếp u. Kết quả tối ưu trong nhánh của v khi v bị loại là `skip[v]`. Vì các cây con của những đứa con khác nhau không có cạnh nối chéo, ta cộng độc lập:

```text
take[u] = w[u] + SUM(skip[v])
                 for all v in children(u)
```

Không được thay `skip[v]` bằng 0 một cách máy móc. Việc không chọn v **không đồng nghĩa** bỏ toàn bộ cây con của v: có thể vẫn chọn các hậu duệ đem lại trọng số dương.

### Trường hợp không chọn u

Nếu không chọn u thì từng đứa con v **được quyền chọn hoặc không chọn**, miễn phương án trong chính cây con v là độc lập. Vì không có cạnh giữa các cây con của những đứa con khác nhau, có thể tối ưu từng nhánh độc lập:

```text
skip[u] = SUM(MAX(take[v], skip[v]))
                 for all v in children(u)
```

**Điểm then chốt:** `take[u]` cần **`skip[v]`**, trong khi `skip[u]` cần **`max(take[v],skip[v])`**.

### Lá và điều kiện gốc

Nếu u là lá, `children(u)` rỗng, tổng trên tập rỗng bằng 0. Vì vậy:

```text
take[u] = w[u]
skip[u] = 0
```

Với một cây chỉ có một đỉnh trọng số 7, đáp án là `max(7,0)=7`. Nếu trọng số -5, đáp án là `max(-5,0)=0` và tập rỗng được chọn.

**Đây không phải DP chọn một nhánh duy nhất.** Công thức sử dụng **SUM trên tất cả con**, bởi tập độc lập có thể chọn các đỉnh thuộc **nhiều nhánh khác nhau**. Bài toán đường đi tối đa hoặc đường kính cây lại có công thức tổng hợp khác, không được dùng nhầm.

## 4. Tính tay trên cây 7 đỉnh

Dùng cây ở mục 1 với trọng số:

```text
w[0]=4
w[1]=2, w[2]=3
w[3]=5, w[4]=1, w[5]=6, w[6]=2
```

Tính trạng thái từ **lá lên gốc**:

| Đỉnh | Con | take[u] | skip[u] | Giải thích |
| ---: | --- | ---: | ---: | --- |
| 3 | Không có | 5 | 0 | Lá. |
| 4 | Không có | 1 | 0 | Lá. |
| 5 | Không có | 6 | 0 | Lá. |
| 6 | Không có | 2 | 0 | Lá. |
| 1 | 3,4 | `2+0+0=2` | `max(5,0)+max(1,0)=6` | Bỏ 1 để có thể chọn cả 3 và 4. |
| 2 | 5,6 | `3+0+0=3` | `max(6,0)+max(2,0)=8` | Bỏ 2 để chọn 5 và 6. |
| 0 | 1,2 | `4+6+8=18` | `max(2,6)+max(3,8)=14` | Chọn 0 cho 18. |

Đáp án:

```text
answer = max(take[0], skip[0])
       = max(18, 14)
       = 18
```

Một tập đỉnh tối ưu là **`{0,3,4,5,6}`**, tổng trọng số `4+5+1+6+2=18`. Các đỉnh được chọn không kề nhau: đỉnh 0 chỉ kề 1 và 2, còn các cháu 3,4,5,6 chỉ kề cha của chúng.

**Một tình huống gốc không được chọn:** vẫn cùng cấu trúc cây, đổi trọng số thành `[1,10,9,1,1,1,1]`. Khi đó:

- `take[1]=10`, `skip[1]=1+1=2`.
- `take[2]=9`, `skip[2]=1+1=2`.
- `take[0]=1+2+2=5`, `skip[0]=10+9=19`.

Đáp án 19, chọn **`{1,2}`** và bỏ gốc 0. Tree DP không mặc định gốc phải được chọn; cả hai trạng thái ở gốc đều phải được xét.

## 5. Giả mã hậu duyệt và chứng minh tính đúng đắn

Bước đầu là **dựng cây có gốc** để xác định cha–con. Sau đó duyệt **postorder** (mọi con trước cha) và tính hai trạng thái.

```text
ALGORITHM MAX_WEIGHT_INDEPENDENT_SET_TREE(tree, weights, root)
    REQUIRE tree is connected and acyclic
    REQUIRE each vertex has a weight

    parent, postorder <- ROOT_AND_POSTORDER(tree, root)

    FOR EACH u IN postorder DO
        take[u] <- weights[u]
        skip[u] <- 0

        FOR EACH v IN children(u) DO
            take[u] <- take[u] + skip[v]
            skip[u] <- skip[u] + MAX(take[v], skip[v])
        END FOR
    END FOR

    RETURN MAX(take[root], skip[root])
END ALGORITHM
```

**Bất biến xử lý:** trước khi tính một đỉnh u, với **mọi con v của u**, hai trạng thái `take[v]` và `skip[v]` đã chính xác cho toàn bộ `subtree(v)`. Hậu duyệt bảo đảm các con được tính trước cha.

### Chứng minh bằng quy nạp theo kích thước cây con

**Cơ sở:** với lá u, chỉ có hai lựa chọn: chọn u để lấy `w[u]`, hoặc bỏ u để lấy tổng 0. Do đó `take[u]=w[u]` và `skip[u]=0` đúng.

**Giả thuyết quy nạp:** các trạng thái của mọi cây con nhỏ hơn `subtree(u)`, đặc biệt các cây con của con v, đã được tính tối ưu theo định nghĩa.

**Bước quy nạp:**

- **Nếu bắt buộc chọn u:** mọi con v phải bị loại do cạnh `(u,v)`. Các nhánh con không giao nhau và không có cạnh nối chéo, nên chọn phương án tối ưu `skip[v]` trong mỗi nhánh rồi cộng với `w[u]` vừa hợp lệ vừa không thể bị một phương án khác vượt qua. Đúng công thức `take[u]`.
- **Nếu bắt buộc bỏ u:** mỗi con v có thể được chọn hoặc bỏ. Với từng nhánh, giá trị tối ưu là `max(take[v],skip[v])`; cộng các giá trị này không tạo xung đột giữa nhánh khác nhau. Đúng công thức `skip[u]`.

Hai trường hợp bao phủ mọi tập độc lập của `subtree(u)), nên hai trạng thái đều tối ưu. Đến gốc, mọi tập độc lập hoặc chọn gốc hoặc không chọn gốc; lấy max là đáp án toàn cây.

**Tính kết thúc:** cây hữu hạn và không có chu trình, mỗi đỉnh được đưa vào quá trình duyệt đúng một lần, từng cạnh được xét hữu hạn lần. Khi xử lý theo postorder, trạng thái cha không cần quay lại tính trạng thái con.

### Độ phức tạp

Với n đỉnh và n-1 cạnh:

- Xây danh sách kề: **O(n)** thời gian/bộ nhớ.
- Dựng parent và thứ tự cha-trước-con: **O(n)**.
- Duyệt theo thứ tự **đảo ngược cha-trước-con** để tính DP: mỗi đỉnh và cạnh được xét O(1) lần, nên **O(n)**.
- Hai mảng `take`, `skip` cùng parent/order: **O(n)** bộ nhớ.
- Phục dựng lựa chọn từ gốc xuống các con: **O(n)** thời gian và O(n) bộ nhớ cho trạng thái lựa chọn/danh sách kết quả.

Tổng thời gian **O(n)** và bộ nhớ **O(n)** cho phiên bản lưu đầy đủ mảng và adjacency. Độ sâu cây có thể là n; phiên bản **đệ quy DFS** có nguy cơ tràn stack trên một đường thẳng rất dài. Vì thế chương trình Java bên dưới xây thứ tự bằng một vòng duyệt lặp và xử lý DP bằng **đảo ngược thứ tự**, tránh phụ thuộc vào ngăn xếp đệ quy của JVM.

## 6. Dựng postorder an toàn bằng duyệt lặp

Trong cây, ta có thể lấy một thứ tự mà **cha xuất hiện trước con**, chẳng hạn từ BFS bắt đầu ở gốc:

```text
parent[root] <- NONE
order <- empty
queue <- [root]

WHILE queue not empty DO
    u <- POP_FRONT(queue)
    APPEND u TO order

    FOR EACH neighbor v OF u DO
        IF v = parent[u] THEN CONTINUE END IF
        REQUIRE v has not been discovered before
        parent[v] <- u
        PUSH_BACK(queue, v)
    END FOR
END WHILE
```

Do `parent[v]` được đặt khi v được phát hiện từ u, mọi đỉnh đều được thêm **sau cha** của nó. Vì thế, khi duyệt `order` **từ cuối về đầu**, mọi con v xuất hiện **trước cha u** trong quá trình tính DP — đủ để áp dụng công thức; không bắt buộc phải là DFS postorder truyền thống.

**Lưu ý:** nếu dùng BFS trên đồ thị có chu trình, việc lấy một cây khung rồi bỏ cạnh còn lại **không** giải đúng bài tập độc lập của đồ thị gốc. Trong các bài tree DP, phải **xác minh giả thiết đầu vào là cây** hoặc được đề bài bảo đảm rõ ràng. Chương trình Java thực hiện kiểm tra cơ bản: `n-1` cạnh, chỉ số hợp lệ, không self-loop, không phát hiện cùng một đỉnh hai lần qua nhiều cạnh và mọi đỉnh đều được thăm.

### Trạng thái rỗng, một đỉnh, rừng cây

- **n=0:** không có đỉnh nào, theo quy ước tập rỗng hợp lệ nên tổng trọng số tối đa bằng **0**.
- **n=1:** chọn đỉnh nếu trọng số **dương**, bỏ nếu trọng số bằng 0 hoặc âm, bởi tie-break của mã Java ưu tiên **không chọn khi hai giá trị bằng nhau**.
- **Rừng cây (forest):** có nhiều thành phần cây rời nhau, không có cạnh nối giữa chúng. Có thể áp dụng tree DP **riêng từng thành phần**, rồi cộng các đáp án tối ưu. Không thể dùng hàm chỉ chấp nhận cây liên thông mà bỏ qua những thành phần khác.
- **Đồ thị có chu trình:** không còn là tree DP đơn giản; bài tập đỉnh độc lập trọng số lớn nhất trên đồ thị tổng quát khó hơn nhiều. Không tự áp dụng công thức hai trạng thái nếu hai nhánh có cạnh liên kết.

## 7. Phục dựng tập đỉnh thay vì chỉ lấy tổng

Nếu chỉ cần **tổng trọng số tối đa**, `max(take[root],skip[root])` đủ. Nếu đề yêu cầu **danh sách các đỉnh đã chọn**, ta có thể đi **từ gốc xuống** sau khi tính xong hai mảng:

1. Nếu **cha của u đã được chọn**, bắt buộc **không chọn u**.
2. Nếu **cha không được chọn**, chọn u khi `take[u] > skip[u]`; ngược lại bỏ u.
3. Với trường hợp `take[u] == skip[u]`, cả hai phương án đều tối ưu; để kết quả xác định, ví dụ này **ưu tiên bỏ u**.
4. Tiếp tục quy tắc trên đối với tất cả con v, truyền trạng thái “u đã chọn hay chưa”.

Giả mã:

```text
ALGORITHM RECONSTRUCT(root, parent, take, skip)
    chosen <- empty set
    stack <- [(root, parentSelected=false)]

    WHILE stack not empty DO
        (u, parentSelected) <- POP(stack)

        IF parentSelected THEN
            selectU <- false
        ELSE
            selectU <- (take[u] > skip[u])
        END IF

        IF selectU THEN ADD u TO chosen END IF

        FOR EACH child v OF u DO
            PUSH(stack, (v, parentSelected=selectU))
        END FOR
    END WHILE

    RETURN chosen
END ALGORITHM
```

**Vì sao phục dựng đúng?** Nếu u đã được chọn, mọi con bị buộc vào trạng thái `skip[v]`; thuật toán truyền `selectU=true` để thực hiện điều này. Nếu u không được chọn, các con được phép tự chọn nhánh có giá trị lớn hơn. Ở trường hợp bằng nhau, chọn trạng thái bỏ vẫn đạt cùng giá trị tối ưu. Như vậy, mọi quyết định đi xuống khớp chính xác trạng thái tối ưu đã tính.

**Không bắt buộc phải lưu cả một bảng lựa chọn hai chiều** cho bài hai trạng thái này: từ `take/skip` và trạng thái chọn của cha đã đủ phục dựng. Nhưng với những bài tree DP phức tạp có phân phối ngân sách giữa nhiều con, có thể phải giữ thêm **lựa chọn tối ưu khi gộp** hoặc tính lại để phục dựng.

Lưu ý: số **chỉ số đỉnh** trong lời giải không đồng nghĩa tổng **trọng số**. Một tập ít đỉnh nhưng có trọng số lớn có thể tốt hơn tập nhiều đỉnh có trọng số thấp.

## 8. Bài toán đối chiếu: phủ đỉnh tối thiểu trên cây

**Phủ đỉnh (vertex cover)** là tập đỉnh `S` sao cho **mỗi cạnh** có **ít nhất một đầu mút** thuộc S. Cần **ít đỉnh nhất**, không phải tổng trọng số lớn nhất. Đây là bài toán khác nhưng cũng chỉ cần hai trạng thái tại gốc cây con.

Đặt:

- `cover1[u]`: số đỉnh ít nhất cần chọn để phủ mọi cạnh **nằm trong subtree(u)**, khi **bắt buộc chọn u**.
- `cover0[u]`: số đỉnh ít nhất cần chọn để phủ mọi cạnh nằm trong subtree(u), khi **bắt buộc bỏ u**.

Với mỗi con v, cạnh `(u,v)` phải có ít nhất một đầu mút được chọn:

**Nếu chọn u**, cạnh `(u,v)` đã được phủ, nên v có thể chọn hoặc bỏ:

```text
cover1[u] = 1 + SUM(MIN(cover0[v], cover1[v]))
                         for v in children(u)
```

**Nếu bỏ u**, phải chọn **mọi con v trực tiếp** để phủ cạnh `(u,v)`:

```text
cover0[u] = SUM(cover1[v])
                 for v in children(u)
```

Với lá u, `cover0[u]=0` và `cover1[u]=1`. Đáp án `min(cover0[root],cover1[root])`.

**Chú ý đổi vai trò max/min:** tập đỉnh độc lập **cấm** chọn hai đầu cạnh và tối đa hóa trọng số; phủ đỉnh **bắt buộc** chọn ít nhất một đầu cạnh và tối thiểu hóa số đỉnh. Cấu trúc hai trạng thái tương tự nhưng **công thức khác nhau**.

Với cây 7 đỉnh ở mục 1, chọn `{1,2}` là một phủ đỉnh đủ 2 đỉnh: các cạnh từ 0 tới 1,2 được phủ; các cạnh từ 1 tới 3,4 được phủ; từ 2 tới 5,6 cũng được phủ. Không thể phủ tất cả các cạnh bằng chỉ một đỉnh vì không có đỉnh nào kề mọi cạnh. Vậy phủ đỉnh tối thiểu có kích thước **2**.

**Quan hệ lý thuyết:** trên mọi đồ thị vô hướng, phần bù của một **tập đỉnh độc lập** là một **phủ đỉnh** và ngược lại. Vì thế `maximum independent set cardinality + minimum vertex cover cardinality = n`, khi cả hai mục tiêu tính theo **số đỉnh**. Đừng thay trực tiếp tổng trọng số độc lập bởi `n - minCover`: điều đó chỉ đúng với **độc lập không trọng số** (mỗi đỉnh trọng số 1) và phủ đỉnh đếm số lượng.

## 9. Java 17+: tree DP lặp, có phục dựng và phủ đỉnh

Chương trình dưới đây:

- Dùng **danh sách kề** cho cây vô hướng được đánh số `0..n-1`.
- Chọn gốc 0 cho cây không rỗng, dựng `parent[]` và `order[]` bằng một lần quét dạng BFS.
- Xử lý `order[]` theo chiều ngược để tính `take[u]`, `skip[u]` trên tất cả cây con.
- Phục dựng nghiệm bằng **ngăn xếp tự quản** thay vì đệ quy, trả danh sách đỉnh theo chỉ số tăng dần.
- Tính **phủ đỉnh tối thiểu không trọng số** bằng hai trạng thái độc lập để đối chiếu.
- Từ chối đồ thị không phải cây, cạnh sai chỉ số, self-loop, cạnh trùng dẫn đến phát hiện chu trình.
- Dùng `Math.addExact` để phát hiện tràn `long` khi cộng trọng số; nếu đề có trọng số/tổng có thể vượt `long`, phải chọn kiểu lớn hơn hoặc `BigInteger`.

Tạo tệp **`SubtreeRootDpDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class SubtreeRootDpDemo {
    record RootedTree(List<List<Integer>> adj,
                      int[] parent, int[] order) {}

    record IndependentSet(long weight, List<Integer> vertices) {}

    private static RootedTree rootTree(int n, int[][] edges) {
        if (n <= 0) {
            throw new IllegalArgumentException("Tree must be nonempty");
        }
        Objects.requireNonNull(edges, "edges");
        if (edges.length != n - 1) {
            throw new IllegalArgumentException("Expected n-1 edges");
        }

        List<List<Integer>> adj = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            adj.add(new ArrayList<>());
        }
        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException("Invalid edge");
            }
            int u = edge[0];
            int v = edge[1];
            if (u < 0 || u >= n || v < 0 || v >= n || u == v) {
                throw new IllegalArgumentException("Invalid endpoint");
            }
            adj.get(u).add(v);
            adj.get(v).add(u);
        }

        int[] parent = new int[n];
        Arrays.fill(parent, -2); // -2 = chưa phát hiện.
        parent[0] = -1;          // Gốc không có cha.
        int[] order = new int[n];
        int head = 0;
        int count = 1;
        order[0] = 0;

        // order vừa là danh sách duyệt vừa là hàng đợi BFS.
        while (head < count) {
            int u = order[head++];
            for (int v : adj.get(u)) {
                if (v == parent[u]) {
                    continue;
                }
                if (parent[v] != -2) {
                    throw new IllegalArgumentException(
                            "Cycle or duplicate edge");
                }
                parent[v] = u;
                order[count++] = v;
            }
        }

        if (count != n) {
            throw new IllegalArgumentException("Disconnected graph");
        }
        return new RootedTree(adj, parent, order);
    }

    public static IndependentSet maxWeightIndependentSet(
            long[] weights, int[][] edges) {
        Objects.requireNonNull(weights, "weights");
        Objects.requireNonNull(edges, "edges");
        int n = weights.length;
        if (n == 0) {
            if (edges.length != 0) {
                throw new IllegalArgumentException("Edges without nodes");
            }
            return new IndependentSet(0L, List.of());
        }

        RootedTree tree = rootTree(n, edges);
        int[] parent = tree.parent();
        int[] order = tree.order();
        List<List<Integer>> adj = tree.adj();

        long[] take = new long[n];
        long[] skip = new long[n];

        // Mọi con nằm SAU cha trong order.
        for (int i = n - 1; i >= 0; i--) {
            int u = order[i];
            long includeU = weights[u];
            long excludeU = 0L;

            for (int v : adj.get(u)) {
                if (parent[v] == u) {
                    includeU = Math.addExact(includeU, skip[v]);
                    excludeU = Math.addExact(excludeU,
                            Math.max(take[v], skip[v]));
                }
            }
            take[u] = includeU;
            skip[u] = excludeU;
        }

        // Phục dựng nghiệm; nếu bằng nhau, ưu tiên bỏ u.
        boolean[] chosen = new boolean[n];
        int[] stack = new int[n];
        boolean[] parentChosen = new boolean[n];
        int size = 0;
        stack[size] = 0;
        parentChosen[size++] = false;

        while (size > 0) {
            size--;
            int u = stack[size];
            boolean forceSkip = parentChosen[size];
            boolean selectU = !forceSkip && take[u] > skip[u];
            chosen[u] = selectU;

            for (int v : adj.get(u)) {
                if (parent[v] == u) {
                    stack[size] = v;
                    parentChosen[size++] = selectU;
                }
            }
        }

        List<Integer> vertices = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            if (chosen[u]) {
                vertices.add(u);
            }
        }

        return new IndependentSet(
                Math.max(take[0], skip[0]),
                List.copyOf(vertices));
    }

    public static int minimumVertexCover(int n, int[][] edges) {
        Objects.requireNonNull(edges, "edges");
        if (n == 0) {
            if (edges.length != 0) {
                throw new IllegalArgumentException("Edges without nodes");
            }
            return 0;
        }

        RootedTree tree = rootTree(n, edges);
        int[] parent = tree.parent();
        int[] order = tree.order();
        List<List<Integer>> adj = tree.adj();

        int[] cover0 = new int[n];
        int[] cover1 = new int[n];

        for (int i = n - 1; i >= 0; i--) {
            int u = order[i];
            int withoutU = 0;
            int withU = 1;

            for (int v : adj.get(u)) {
                if (parent[v] == u) {
                    withoutU = Math.addExact(withoutU, cover1[v]);
                    withU = Math.addExact(withU,
                            Math.min(cover0[v], cover1[v]));
                }
            }
            cover0[u] = withoutU;
            cover1[u] = withU;
        }
        return Math.min(cover0[0], cover1[0]);
    }

    private static void display(
            String name, long[] weights, int[][] edges) {
        IndependentSet result =
                maxWeightIndependentSet(weights, edges);
        System.out.println(name + "=" + result.weight() +
                " nodes=" + result.vertices());
    }

    public static void main(String[] args) {
        int[][] edges = {
            {0, 1}, {0, 2}, {1, 3}, {1, 4},
            {2, 5}, {2, 6}
        };

        display("main", new long[]{4, 2, 3, 5, 1, 6, 2},
                edges);
        System.out.println("cover=" + minimumVertexCover(7, edges));

        display("rootSkipped", new long[]{1, 10, 9, 1, 1, 1, 1},
                edges);

        int[][] pathEdges = {{0, 1}, {1, 2}, {2, 3}};
        display("path", new long[]{5, 1, 4, 3}, pathEdges);

        int[][] negativeEdges = {{0, 1}, {1, 2}};
        display("negative", new long[]{-5, -2, -7},
                negativeEdges);

        display("single", new long[]{7}, new int[0][]);
        System.out.println("singleCover=" +
                minimumVertexCover(1, new int[0][]));

        display("empty", new long[0], new int[0][]);
        System.out.println("emptyCover=" +
                minimumVertexCover(0, new int[0][]));

        display("tie", new long[]{0, 0}, new int[][]{{0, 1}});
        System.out.println("tieCover=" +
                minimumVertexCover(2, new int[][]{{0, 1}}));
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac SubtreeRootDpDemo.java
java SubtreeRootDpDemo
```

**Đầu ra xác định:**

```text
main=18 nodes=[0, 3, 4, 5, 6]
cover=2
rootSkipped=19 nodes=[1, 2]
path=9 nodes=[0, 2]
negative=0 nodes=[]
single=7 nodes=[0]
singleCover=0
empty=0 nodes=[]
emptyCover=0
tie=0 nodes=[]
tieCover=1
```

### Cách đọc kết quả

- `main`: chọn gốc 0 và các cháu 3,4,5,6, tổng 18. Hai con 1,2 bị bỏ vì kề trực tiếp gốc.
- `cover=2`: chọn hai đỉnh 1,2 đủ phủ tất cả các cạnh; đây là bài toán **khác** với tổng trọng số độc lập.
- `rootSkipped`: hai đỉnh 1,2 có trọng số 10 và 9; bỏ gốc 0 để đạt tổng 19.
- `path`: trên đường `0—1—2—3`, chọn các đỉnh 0 và 2 có tổng 5+4=9 và không kề nhau.
- `negative`: mọi trọng số âm; tập rỗng có tổng 0 lớn hơn bất kỳ tập không rỗng nào.
- `single`: cây một đỉnh trọng số 7, chọn chính đỉnh đó. Không có cạnh nào cần phủ nên `singleCover=0`.
- `empty`: cây rỗng theo quy ước không có cạnh và tập đỉnh độc lập tối ưu có tổng 0.
- `tie`: hai đỉnh trọng số 0 có nhiều lựa chọn cùng tổng 0; do mã chọn **skip khi hòa**, trả tập rỗng. Cây một cạnh vẫn cần ít nhất một đỉnh để phủ cạnh nên `tieCover=1`.

**Giới hạn:** mã dành cho **một cây liên thông**, không phải đồ thị bất kỳ. Đối với `n=0`, hàm trả kết quả rỗng theo quy ước. Trọng số `long` có thể âm; vì thế không dùng sentinel `-1` làm dấu trạng thái chưa tính. `Math.addExact` phát hiện tràn thay vì âm thầm cho tổng sai; không nên bắt lỗi này rồi coi như đã có đáp án.

**Về bộ nhớ:** danh sách kề, `parent`, `order`, các mảng trạng thái và ngăn xếp phục dựng đều tốn O(n). Không có đệ quy theo chiều cao cây nên tránh lỗi tràn call stack cho cây dạng dây rất dài, dù với dữ liệu n lớn vẫn cần bộ nhớ tuyến tính.

## 10. Những công thức tree DP cùng mẫu tổng hợp

Hai trạng thái chọn/bỏ là một **mẫu**. Tùy ràng buộc, phần trạng thái ở gốc cây con cần lưu có thể khác:

| Bài toán | Trạng thái ở u | Cách tổng hợp con |
| --- | --- | --- |
| Tập đỉnh độc lập trọng số lớn nhất | `take[u]`, `skip[u]` | Chọn u ⇒ mọi con bị bỏ; bỏ u ⇒ con tự chọn tối ưu. |
| Phủ đỉnh nhỏ nhất | `cover1[u]`, `cover0[u]` | Chọn u ⇒ con tùy ý; bỏ u ⇒ phải chọn tất cả con. |
| Đếm số cách tô hai màu hợp lệ | Số phương án khi u có màu 0/1 | Nhân số cách của các con tương ứng với màu được phép. |
| Đếm số tập độc lập | `ways1[u]`, `ways0[u]` | `ways1[u]=∏ways0[v]`; `ways0[u]=∏(ways0[v]+ways1[v])`. |
| Đường đi dài nhất/đường kính | Độ dài nhánh tốt nhất đi xuống từ u | Chọn một hoặc hai nhánh con phù hợp, không cộng mọi nhánh một cách mù quáng. |
| Ba lô trên cây | `dp[u][k]` với ngân sách/số đỉnh k | Gộp các con bằng tích chập kiểu knapsack, thường tốn nhiều hơn O(n). |

**Ví dụ đếm tập độc lập:** nếu không quan tâm trọng số mà muốn **đếm** mọi tập độc lập trên cây, kể cả tập rỗng, có thể đặt:

```text
waysTake[u] = PRODUCT(waysSkip[v])
                     over all children v

waysSkip[u] = PRODUCT(waysTake[v] + waysSkip[v])
                     over all children v

answer = waysTake[root] + waysSkip[root]
```

Lá có `waysTake=1`, `waysSkip=1`, vì mỗi trạng thái có đúng một cách chọn trong cây một đỉnh (chọn hoặc bỏ). Với cây một cạnh, số tập độc lập là 3: `{}`, `{u}`, `{v}`. Nếu cần kết quả modulo một số `M`, phải thực hiện **mọi phép cộng/nhân** theo modulo đúng chỗ. Nếu cần đếm chính xác số cách cho cây lớn, kiểu số nguyên có thể tràn và cần xử lý riêng.

Điều này cho thấy **cấu trúc gốc cây con** giữ nguyên, nhưng phép kết hợp có thể là **max/sum**, **min/sum** hoặc **sum/product**. Không được sao chép công thức từ bài tối ưu sang bài đếm mà quên đổi ý nghĩa trạng thái.

## 11. Rerooting và khi nào trạng thái cây con chưa đủ

Các công thức đã học tính đáp án **toàn cây với một gốc đã chọn**. Nếu bài toán yêu cầu **đáp án khi coi từng đỉnh là gốc** hoặc **tổng khoảng cách từ mỗi đỉnh tới mọi đỉnh**, trạng thái chỉ chứa đóng góp từ **cây con phía dưới** có thể chưa đủ. Ta cần đưa thông tin từ **phía cha và các anh em** vào mỗi đỉnh.

Kỹ thuật **đổi gốc (rerooting DP)** thường gồm:

1. Một lượt **postorder** tính đóng góp từ các cây con.
2. Một lượt **preorder** chuyển đóng góp “từ ngoài cây con” xuống từng đứa con.
3. Tổng hợp đóng góp từ mọi hướng để có kết quả ứng với từng gốc.

Ví dụ, muốn tính `sumDistance[u]` là tổng khoảng cách từ u đến mọi đỉnh trên một cây n đỉnh, có thể dùng `size[u]` là số đỉnh trong cây con u và một công thức đổi gốc:

```text
sumDistance[child] =
    sumDistance[parent] + n - 2 * size[child]
```

Mỗi bước chuyển gốc đi qua một cạnh làm khoảng cách tới `size[child]` đỉnh trong cây con giảm 1, còn khoảng cách tới `n-size[child]` đỉnh ngoài cây con tăng 1. Vì vậy tổng thay đổi bằng `(n-size[child])-size[child]=n-2*size[child]`.

Đây là **ví dụ mở rộng** về DP cấu trúc cây, không phải công thức của tập độc lập trọng số lớn nhất. Với bài độc lập trọng số lớn nhất khi chỉ cần **một đáp án toàn cây**, một gốc và hai trạng thái tại mỗi đỉnh đã đủ; không cần rerooting.

### Khi số trạng thái cần tăng

Hai trạng thái chọn/bỏ chỉ đủ vì **ảnh hưởng của cây con tới phần ngoài** được quyết định hoàn toàn bởi việc chọn hay bỏ đỉnh u. Nếu một ràng buộc cần biết thêm:

- Tổng số đỉnh đã chọn trong cây con.
- Ngân sách hoặc tổng trọng lượng tối đa.
- Màu của cha và u trong một bảng màu lớn hơn.
- Số cạnh đã dùng trong một ghép cặp.
- Có hay chưa có một đỉnh đặc biệt được chọn.

thì trạng thái phải có **các tham số bổ sung**. Cần xác định “thông tin nào của cây con đủ để kết hợp với phần còn lại” thay vì cố nhồi mọi bài vào đúng hai biến.

## 12. Phân tích khi đầu vào không phải một cây chuẩn

### Cây dạng dây và cây hình sao

Cây dạng dây có chiều cao có thể đến n-1 nếu đặt gốc ở một đầu. DFS đệ quy dễ có nguy cơ `StackOverflowError` trên JVM ở n rất lớn. Thuật toán lặp ở mục 9 không đệ quy, nên **độ sâu không ảnh hưởng call stack**, vẫn O(n) bộ nhớ cho cấu trúc dữ liệu.

Cây hình sao có một gốc kề rất nhiều lá. Công thức `take[root]` cộng `skip` của tất cả lá, trong khi `skip[root]` cộng `max(take,skip)` của từng lá. Phải xử lý được số con lớn, không được giả sử mỗi đỉnh có tối đa hai con.

### Rừng cây

Nếu đồ thị gồm `k` thành phần, mỗi thành phần là một cây, tối ưu toàn rừng là **tổng** đáp án tối ưu của từng thành phần, vì các thành phần không có cạnh nối. Có thể khởi tạo một lượt duyệt cho mỗi đỉnh chưa được phát hiện, lưu root của từng thành phần, rồi cộng `max(take[root],skip[root])` cho các root đó.

**Không được lấy kết quả của riêng root=0 cho cả rừng.** Hàm Java ở đây cố tình từ chối trường hợp không liên thông thay vì trả một kết quả thiếu. Nếu đề bài cho rừng, cần sửa rõ đầu vào/duyệt và tổng hợp để hỗ trợ nhiều gốc.

### Trọng số âm và buộc chọn ít nhất một đỉnh

Vì tập rỗng được phép, `skip[u]≥0` trên mọi cây con: ta có thể bỏ mọi đỉnh. Khi toàn bộ trọng số âm, đáp án là 0. Nếu đề bài đòi chọn **ít nhất một đỉnh**, kết quả này không hợp lệ. Phải định nghĩa trạng thái có/không chọn ít nhất một đỉnh, hoặc tính riêng một trường hợp đảm bảo đã có đỉnh được chọn. Không được sửa bằng cách lấy max(0,...) rồi cho rằng đã đáp ứng điều kiện không rỗng.

### Trọng số lớn

Tổng tối ưu có thể vượt `int`, nên thường cần `long`. Với `long`, vẫn có thể tràn nếu trọng số cực lớn hoặc số đỉnh nhiều; mã dùng `Math.addExact` để báo lỗi. Nếu đặc tả cho số nguyên tùy ý, cần `BigInteger` và các phép cộng/so sánh tương ứng. Độ phức tạp O(n) khi coi cộng/so sánh là hằng thời gian; với số nguyên rất lớn, chi phí bit còn phụ thuộc kích thước các giá trị.

## 13. Lỗi phổ biến khi làm DP gốc cây con

1. **Không phân biệt cha và con.** Trên danh sách kề vô hướng, duyệt lại cha dễ dẫn tới vòng lặp vô hạn hoặc cộng trùng.
2. **Tính cha trước khi có trạng thái con.** Công thức dùng giá trị chưa khởi tạo; phải dùng hậu duyệt hoặc đảo thứ tự cha-trước-con.
3. **Chọn u nhưng vẫn dùng `max(take[v],skip[v])` ở con.** Có thể chọn đồng thời u và v, vi phạm điều kiện độc lập.
4. **Bỏ u rồi chỉ lấy `skip[v]` của mọi con.** Vô tình cấm chọn các con mặc dù u đã bị bỏ, làm mất phương án tối ưu.
5. **Chọn u và bỏ luôn toàn bộ cây con.** Cháu của u không kề u; chúng vẫn có thể được chọn, nên phải dùng `skip[v]` chứ không phải 0.
6. **Dùng max của các nhánh thay vì tổng.** Tập độc lập được chọn trong **nhiều nhánh**, cần cộng các đóng góp độc lập.
7. **Không định nghĩa đúng điều kiện tại gốc cây con.** `take[u]` buộc chọn u và `skip[u]` buộc bỏ u; đó là lý do công thức có thể kết hợp.
8. **Lấy `take[root]` làm đáp án mặc định.** Gốc có thể không thuộc phương án tối ưu.
9. **Tưởng một cây có nhiều gốc thật.** Chọn root chỉ phục vụ thuật toán; bài toán vô hướng không đổi.
10. **Áp dụng công thức trên đồ thị có chu trình.** Các cây con không còn độc lập; bỏ cạnh tạo cây khung không giữ nguyên ràng buộc gốc.
11. **Lẫn bài independent set với vertex cover.** Hai bài có công thức ngược điều kiện và mục tiêu max/min khác nhau.
12. **Bỏ qua các trường hợp bằng nhau khi phục dựng.** Cần quy tắc phá hòa nếu muốn danh sách kết quả xác định.
13. **Giải bài trọng số âm nhưng buộc chọn một đỉnh mà vẫn cho tập rỗng.** Phải đổi trạng thái theo đặc tả.
14. **Không tính ngăn xếp đệ quy.** Với cây dây dài, phiên bản đệ quy có thể tràn stack dù lý thuyết O(n).
15. **Dùng `-1` để đánh dấu DP chưa tính khi giá trị có thể âm.** Có thể lẫn một giá trị tối ưu thực với sentinel.
16. **Không xử lý n=0 hoặc n=1.** Đáp án phụ thuộc quy ước tập rỗng và trạng thái lá.
17. **Chỉ tính giá trị nhưng đề bài yêu cầu đỉnh đã chọn.** Cần phục dựng từ trạng thái đã lưu.
18. **Báo O(n) cho mọi dạng tree DP.** Nếu trạng thái thêm ngân sách k và gộp nhiều con bằng tích chập, thời gian có thể lớn hơn O(n).
19. **Cộng trọng số trong `int` không kiểm soát tràn.** Kết quả có thể sai dù công thức đúng.
20. **Cho rằng đổi gốc luôn cần thiết.** Khi chỉ hỏi đáp án toàn cây của tập độc lập, một lần root + postorder đã đủ.

## 14. Bài tập tự luyện có lời giải

**Câu 1.** Cây chỉ có một đỉnh u trọng số 9. Tính `take[u]`, `skip[u]` và đáp án. **Lời giải:** `take=9`, `skip=0`, tối ưu 9, chọn u.

**Câu 2.** Cây một đỉnh trọng số -7, được phép chọn tập rỗng. Đáp án là bao nhiêu? **Lời giải:** `max(-7,0)=0`; không chọn đỉnh nào.

**Câu 3.** Với cây gồm một cạnh `(0,1)`, trọng số `[8,5]`, có thể chọn hai đỉnh cùng lúc không? Đáp án? **Lời giải:** không, vì chúng kề nhau. Chọn 0 có tổng 8, chọn 1 có tổng 5, bỏ cả hai được 0. Đáp án 8.

**Câu 4.** Với cây gốc u có hai con lá v và t trọng số `w[u]=3`, `w[v]=4`, `w[t]=5`, tính hai trạng thái ở u. **Lời giải:** `take[u]=3+0+0=3`; `skip[u]=max(4,0)+max(5,0)=9`; đáp án 9, chọn v và t.

**Câu 5.** Với cây 7 đỉnh và trọng số `[4,2,3,5,1,6,2]`, một tập tối ưu là gì? **Lời giải:** `{0,3,4,5,6}` có tổng 18; công thức ở gốc cho `take[0]=18`, `skip[0]=14`, nên tối ưu 18.

**Câu 6.** Vì sao trong `take[u]` dùng `skip[v]` thay vì `max(take[v],skip[v])`? **Lời giải:** vì chọn u cấm chọn mọi con v trực tiếp, do có cạnh `(u,v)`. `max` có thể chọn v và tạo nghiệm không hợp lệ.

**Câu 7.** Nếu u không được chọn, tại sao các con khác nhau có thể được tối ưu riêng rồi **cộng**? **Lời giải:** trong cây, các cây con của các con khác nhau không giao nhau và không có cạnh nối giữa chúng; các lựa chọn trong nhánh này không gây xung đột với nhánh kia.

**Câu 8.** Trong phủ đỉnh tối thiểu, nếu bỏ u thì các con v phải ở trạng thái nào? **Lời giải:** bắt buộc `cover1[v]` vì cạnh `(u,v)` phải được phủ và u không được chọn.

**Câu 9.** Cây dạng dây có 100.000 đỉnh. Vì sao phiên bản Java đệ quy đơn giản có rủi ro? **Lời giải:** nếu đặt gốc ở một đầu, độ sâu đệ quy có thể 100.000, gây `StackOverflowError`. Có thể dựng `order` bằng vòng lặp rồi xử lý đảo ngược.

**Câu 10.** Nếu cần vừa tối ưu tổng trọng số vừa phục dựng danh sách các đỉnh được chọn, chỉ trả `answer` có đủ không? **Lời giải:** không. Có thể lưu `take/skip` rồi đi từ gốc xuống theo trạng thái cha để chọn một nghiệm tối ưu.

**Câu 11.** Một đồ thị có hai thành phần, mỗi thành phần là cây. Có thể chỉ gọi DP từ đỉnh 0 rồi coi đó là kết quả cho toàn bộ không? **Lời giải:** không. Phải tính và cộng kết quả cho **từng thành phần**, hoặc biến đổi đầu vào phù hợp mà không thay đổi điều kiện bài toán.

**Câu 12.** Với cây một cạnh, có bao nhiêu tập đỉnh độc lập kể cả tập rỗng? **Lời giải:** 3: rỗng, chỉ đỉnh thứ nhất, chỉ đỉnh thứ hai. Không được chọn cả hai.

**Câu 13.** Tree DP phải luôn dùng hai trạng thái không? **Lời giải:** không. Hai trạng thái đủ ở bài chọn/bỏ u vì ràng buộc tới cha chỉ phụ thuộc việc u có được chọn. Bài có ngân sách, màu hoặc số lượng đỉnh có thể cần thêm tham số.

**Câu 14.** Tại sao `sumDistance[child]=sumDistance[parent]+n-2*size[child]` trong rerooting khoảng cách? **Lời giải:** khi chuyển gốc từ parent sang child, khoảng cách tới `size[child]` đỉnh giảm 1, còn tới `n-size[child]` đỉnh tăng 1; tổng biến đổi bằng `n-2*size[child]`.

**Câu 15.** Với cây 7 đỉnh ở mục 1, phủ đỉnh tối thiểu cần bao nhiêu đỉnh? **Lời giải:** 2; chọn `{1,2}` phủ đủ cả sáu cạnh, và không thể phủ tất cả bằng một đỉnh.

## 15. Checklist triển khai tree DP với trạng thái ở gốc cây con

1. **Đầu vào đúng là cây?** Nếu là rừng hoặc đồ thị tổng quát, có cần xử lý từng thành phần hay thuật toán khác?
2. **Đã chọn root và xây parent/children đúng chưa?** Không duyệt cha như một con.
3. **Trạng thái `dp[u][state]` mang ý nghĩa chính xác gì?** Điều kiện liên quan tới việc u được chọn/bỏ/nhận một nhãn là gì?
4. **Có bao nhiêu thông tin phải truyền qua cạnh cha–con?** Chỉ một bit chọn/bỏ hay còn ngân sách, màu, số lượng?
5. **Lá được khởi tạo đúng chưa?** Tổng rỗng bằng 0, tích rỗng bằng 1 nếu đang đếm cách; các ràng buộc đặc biệt phải nhất quán.
6. **Công thức tổng hợp con có đúng ngữ nghĩa không?** Chọn u ⇒ con bị bỏ trong tập độc lập, nhưng lại cho phép con tùy ý trong phủ đỉnh.
7. **Thứ tự xử lý bảo đảm con trước cha chưa?** Dùng postorder hoặc đảo thứ tự cha-trước-con.
8. **Đáp án ở gốc là max/min/tổng của các trạng thái nào?** Không mặc định chọn gốc.
9. **Có cần phục dựng lựa chọn không?** Lưu đủ `take/skip` và trạng thái cha hoặc thông tin gộp bổ sung.
10. **Có trọng số âm, đáp án bằng 0 hoặc trường hợp n=0 không?** Xác định tập rỗng có hợp lệ.
11. **Có giới hạn chiều cao cây hoặc độ lớn trọng số không?** Cân nhắc duyệt lặp, `long`/`BigInteger` và tràn số.
12. **Độ phức tạp tính theo số cạnh, số trạng thái và chi phí gộp chưa?** Với hai trạng thái và phép cộng mỗi cạnh, là O(n).
13. **Đã thử cây dây, cây sao, một đỉnh, nhiều đỉnh đồng trọng số, toàn số âm và dữ liệu sai cấu trúc chưa?** Các ca này dễ phát hiện thiếu trạng thái hoặc lỗi duyệt.

**Ghi nhớ:** tree DP không bắt đầu từ việc “ghi nhớ đáp án toàn cây” mà từ việc **tóm tắt bài toán của mỗi cây con bằng những trạng thái đủ thông tin để kết hợp với cha**. Với tập đỉnh độc lập, đó là hai trạng thái `take[u]` và `skip[u]`; xử lý con trước cha và dùng đúng điều kiện cạnh giúp biến bài toán có `2^n` khả năng chọn thành lời giải **O(n)** trên cây.

# Tô màu đồ thị bằng số màu giới hạn

**Tô màu đồ thị với số màu giới hạn** (*graph k-coloring / m-coloring*) là bài toán quyết định xem có thể gán cho mỗi **đỉnh** của một **đồ thị vô hướng** một màu trong tập có tối đa k màu, sao cho **hai đỉnh kề nhau luôn có màu khác nhau**, hay không. Đây là ví dụ điển hình của **quay lui (backtracking)**: xây dựng lời giải từng bước, từ chối ngay những lựa chọn vi phạm ràng buộc, và quay về thử màu khác khi nhánh hiện tại không thể hoàn thành.

Điểm khác biệt với một thuật toán tham lam chỉ chọn màu đầu tiên có vẻ phù hợp là **quay lui không kết luận thất bại khi một chuỗi lựa chọn ban đầu đi vào ngõ cụt**. Nó phục hồi trạng thái và thử các khả năng khác. Nếu thuật toán duyệt đầy đủ các lựa chọn hợp lệ (và chỉ cắt những nhánh đã được chứng minh không có nghiệm), nó sẽ tìm được lời giải khi tồn tại và trả lời **không thể** khi đã loại bỏ tất cả phương án.

Bài học trình bày mô hình hóa, bất biến, giả mã, hai chiến lược chọn đỉnh (thứ tự cố định và **DSATUR**), cách kiểm tra ràng buộc, **forward checking**, chứng minh tính đúng, độ phức tạp, những trường hợp biên và chương trình **Java 17+** tự biên dịch/chạy được.

## 1. Phát biểu chính xác bài toán

Cho đồ thị vô hướng `G=(V,E)` với `n=|V|` đỉnh, đánh số 0..n−1, và số nguyên `k≥0`. Tìm hàm màu:

```text
color: V -> {1, 2, ..., k}

với mọi cạnh vô hướng {u,v} thuộc E:
    color[u] != color[v]
```

Nếu tồn tại một phép gán thỏa điều kiện, gọi đồ thị là **k-colorable**; ta có thể trả một mảng màu độ dài n. Nếu không tồn tại, trả `false` hoặc một kết quả thể hiện không có nghiệm.

**Mục tiêu của bài này là dùng tối đa k màu**, không bắt buộc sử dụng hết cả k màu. Chẳng hạn một chu trình chẵn có thể tô đúng bằng 2 màu thì cũng **k-colorable với k=3 hoặc k=4**, dù lời giải chỉ dùng hai màu thực sự.

**Không phải tô màu cạnh.** Ở bài tô màu đỉnh, các đỉnh kề nhau cần khác màu; hai cạnh cùng đỉnh không được yêu cầu khác màu. Bài tô màu cạnh (*edge coloring*) có đối tượng và giới hạn khác, không được dùng trực tiếp công thức dưới đây.

### Một tô màu hợp lệ phải thỏa cả hai nhóm điều kiện

1. **Miền màu:** Mỗi đỉnh được gán một số nguyên từ 1 tới k; không để sót đỉnh.
2. **Ràng buộc cạnh:** Mọi cạnh {u,v} đều có `color[u] != color[v]`.

Trong lúc quay lui, giá trị **0** được dùng như dấu **chưa tô**; 0 **không phải một màu hợp lệ** của kết quả cuối.

### Ví dụ cơ bản

Đồ thị tam giác:

```text
     0
    / \
   1---2

Cạnh: (0,1), (1,2), (2,0)
```

Với k=2, không thể tô hợp lệ: nếu 0 màu 1 thì cả 1 và 2 phải màu 2, nhưng chúng kề nhau. Với k=3, có thể tô `[1,2,3]` theo chỉ số đỉnh 0,1,2.

Đồ thị chu trình bốn đỉnh:

```text
0 ----- 1
|       |
|       |
3 ----- 2

Cạnh: (0,1), (1,2), (2,3), (3,0)
```

Với k=2, một tô màu hợp lệ là `[1,2,1,2]`. Hai đỉnh không kề nhau **được phép cùng màu**.

## 2. Những giả thiết đầu vào cần xác định

Bài toán chuẩn trong chương trình Java dùng **đồ thị vô hướng đơn**:

- Mỗi đỉnh có chỉ số nguyên 0..n−1.
- Mỗi cạnh đầu vào là cặp [u,v]; chương trình tự tạo cả hai quan hệ kề `adj[u][v]` và `adj[v][u]`.
- **Không có khuyên (self-loop)** {v,v}. Một đỉnh kề chính nó sẽ đòi `color[v] != color[v]`, điều không thể thỏa với bất kỳ màu nào. Mã Java **từ chối** self-loop bằng ngoại lệ để giữ hợp đồng “đồ thị đơn”; một API khác có thể trả `impossible`, nhưng phải nói rõ quy ước.
- Cạnh trùng lặp không tạo ràng buộc mới và được gộp khi dựng ma trận kề.
- Đồ thị có thể không liên thông; mọi thành phần liên thông đều cần được tô.
- Số màu k không âm; nếu n>0 và k=0 thì không thể tô vì không có màu nào để chọn.
- Với đồ thị rỗng n=0, mảng tô màu rỗng **là nghiệm hợp lệ** kể cả k=0.

Không nên tự coi dữ liệu hướng là vô hướng. Nếu đề bài yêu cầu tô **đồ thị có hướng**, phải nói rõ quan hệ xung đột (thường bỏ hướng cạnh khi kiểm tra hai đầu) rồi chuyển thành mô hình thích hợp.

### “Có nhiều màu hơn số đỉnh” có làm khó thêm không?

Đối với đồ thị vô hướng đơn n đỉnh, **n màu luôn đủ**: gán một màu khác nhau cho từng đỉnh. Vì vậy nếu k>n, trong bài chỉ yêu cầu **tối đa k màu**, có thể giới hạn bảng màu thực tế tại:

```text
effectiveK = min(k, n)
```

Điều này không làm mất nghiệm: nếu k≥n thì chắc chắn có nghiệm cho n>0, và mọi phương án dùng ≤n màu cũng dùng ≤k màu. Mã Java dùng giới hạn này để tránh cấp phát một mảng lớn khi k có giá trị cực lớn. Đối với n=0, trả nghiệm rỗng trước khi đệ quy.

## 3. Khác biệt giữa bài quyết định, tìm nghiệm, đếm nghiệm và sắc số

Các bài nghe tương tự nhưng có đầu ra khác nhau:

| Bài toán | Câu hỏi/đầu ra |
| --- | --- |
| **k-colorability (quyết định)** | Có tồn tại tô màu bằng **tối đa k màu** hay không? |
| **Tìm một phép tô màu** | Trả về một mảng màu hợp lệ hoặc báo không có nghiệm |
| **Đếm số phép tô màu** | Có bao nhiêu phép gán màu hợp lệ, theo quy ước màu có nhãn? |
| **Sắc số** `χ(G)` | Số màu **ít nhất** cần để tô đồ thị |
| **List coloring** | Mỗi đỉnh có **danh sách màu riêng**; phải chọn trong danh sách đó |
| **Precoloring extension** | Một số đỉnh đã có màu cố định; cần mở rộng không thay đổi màu đã khóa |

Chương trình ở đây giải **quyết định và tìm một nghiệm**, không đếm hết tất cả nghiệm và không trực tiếp tối thiểu hóa số màu. Muốn tìm sắc số cho đồ thị nhỏ, có thể thử k từ cận dưới đến cận trên và dùng bộ giải quyết định; cách làm ấy vẫn có chi phí rất lớn trong trường hợp xấu.

**Không được nhầm số cách gán với số cách phân lớp không phân biệt tên màu.** Nếu dùng màu nhãn 1,2,3 thì việc hoán đổi tên màu có thể tạo nhiều cách gán khác nhưng cùng phân hoạch đỉnh. Bài đếm phải định nghĩa rõ đang coi các màu có phân biệt hay không.

## 4. Quay lui biểu diễn bài toán như thế nào?

Ta duy trì mảng `color[0..n−1]`:

- `color[v]=0`: đỉnh v chưa được tô.
- `color[v]=c`, 1≤c≤k: đỉnh v đã được tô màu c.

Ở mỗi bước:

1. Chọn một **đỉnh chưa tô** v.
2. Lần lượt thử các màu c từ 1 đến k.
3. Chỉ tạm gán c nếu **không có hàng xóm đã tô nào** của v mang màu c.
4. Sau khi gán, giải đệ quy phần còn lại.
5. Nếu hoàn thành tất cả đỉnh, trả thành công.
6. Nếu nhánh thất bại, **hoàn tác** `color[v]=0` và thử màu kế tiếp.
7. Nếu mọi màu đều không thành công, trả thất bại cho cấp gọi trước.

Thuật toán chỉ cần kiểm tra xung đột với **những đỉnh đã có màu**, không cần thử nghiệm các màu của đỉnh chưa tô trong hàm kiểm tra cục bộ. Ràng buộc còn lại sẽ được kiểm tra khi các đỉnh đó được tô về sau.

### Cây tìm kiếm

Mỗi nút của cây tìm kiếm là một **phép gán màu từng phần**. Mỗi nhánh là việc chọn màu cho một đỉnh. Nếu luôn có k màu có thể thử, cây tìm kiếm thô có tối đa k lựa chọn ở mỗi trong n mức, nghĩa là cỡ `k^n` phép gán ở lá. Kiểm tra xung đột và cắt nhánh giúp giảm đáng kể số nút trong nhiều trường hợp, nhưng **không xóa được cận mũ trong trường hợp xấu**.

```text
                 chưa tô đỉnh nào
                  /    |    \
             v0=1    v0=2   ... v0=k
             / | \    ...
          v1=1 v1=2 ...
            X    |
     xung đột   tiếp tục

Khi nhánh X không còn màu hợp lệ:
  color[v] = 0
  quay về thử màu tiếp theo của lựa chọn trước
```

Điều quan trọng của **backtracking** là **phục hồi trạng thái đầy đủ**. Nếu hàm đệ quy gán rồi không đặt lại color[v]=0 sau nhánh thất bại, các nhánh sau sẽ nhìn thấy màu “rác” từ một đường đi không còn được chọn và có thể trả kết quả sai.

## 5. Thuật toán quay lui cơ bản theo thứ tự đỉnh

Đơn giản nhất là tô đỉnh theo thứ tự cố định 0,1,...,n−1:

```text
BACKTRACK(v):
    if v == n:
        return true  // đã tô tất cả đỉnh

    for c = 1..k:
        if SAFE(v,c):
            color[v] = c

            if BACKTRACK(v+1):
                return true

            color[v] = 0  // hoàn tác

    return false

SAFE(v,c):
    for u = 0..n-1:
        if adjacent(v,u) and color[u] == c:
            return false
    return true
```

Gọi ban đầu là `BACKTRACK(0)` với color toàn 0.

Nếu tìm thấy nghiệm, dừng ngay ở lời giải đầu tiên hợp lệ. Nếu hàm trả false ở gốc, mọi lựa chọn màu hợp lệ theo thứ tự đỉnh đã được xét hoặc bị loại vì xung đột, nên **không có nghiệm** trong k màu.

### Bất biến quan trọng

Tại đầu mỗi lời gọi quay lui:

- Những đỉnh đã tô có màu trong 1..k.
- Không có cạnh nào nối hai đỉnh đã tô cùng màu.
- Những đỉnh chưa tô có color=0.
- Mỗi mức đệ quy chỉ kiểm soát màu của **một đỉnh được chọn**, và phải trả màu ấy về 0 nếu nhánh không thành công.

Kiểm tra `SAFE(v,c)` bảo toàn bất biến khi thêm một đỉnh. Đặt `color[v]=0` khôi phục bất biến của cấp gọi trước.

**Không cần kiểm tra toàn bộ đồ thị từ đầu** ở mỗi lần gán: những cạnh giữa hai đỉnh đã tô trước đó đã được chứng minh hợp lệ. Chỉ những cạnh liên quan đến đỉnh v mới có thể trở thành xung đột mới.

## 6. Một ví dụ mà tham lam thất bại nhưng quay lui tìm được nghiệm

Xét đồ thị **đường đi gồm bốn đỉnh** trong thứ tự cạnh:

```text
0 -- 2 -- 3 -- 1

Các cạnh: (0,2), (2,3), (3,1)
Giới hạn: k=2
Thứ tự gán màu cố định: đỉnh 0,1,2,3
```

Một thuật toán chỉ lấy **màu hợp lệ nhỏ nhất** và **không quay lui** hoạt động:

1. Đỉnh 0 chưa có hàng xóm được tô → lấy màu 1.
2. Đỉnh 1 chưa có hàng xóm được tô → cũng lấy màu 1.
3. Đỉnh 2 kề đỉnh 0 màu 1 → phải lấy màu 2.
4. Đỉnh 3 kề cả đỉnh 1 màu 1 và đỉnh 2 màu 2 → **không còn màu**.

Nếu kết luận “đồ thị không 2-colorable” tại đây, thuật toán sai. Thực tế có nghiệm:

```text
color[0]=1
color[1]=2
color[2]=2
color[3]=1

Các cạnh:
(0,2): 1 != 2
(2,3): 2 != 1
(3,1): 1 != 2
```

Quay lui có thể trở lại **đỉnh 1**, đổi màu của nó từ 1 sang 2, rồi hoàn tất. Điều này chứng minh rằng “một thứ tự gán và lựa chọn màu thất bại” **không tương đương** với “không tồn tại tô màu hợp lệ”.

**Lưu ý:** Graph này có thể tô bằng 2 màu trong thời gian tuyến tính bằng thuật toán kiểm tra hai phía (*bipartite checking*) vì k=2. Ví dụ nhằm minh họa cơ chế quay lui, không khuyên dùng backtracking làm cách nhanh nhất cho mọi k.

## 7. Chọn đỉnh nào trước? Heuristic DSATUR

Thứ tự 0..n−1 dễ cài đặt và chứng minh, nhưng có thể thử nhiều nhánh không cần thiết. Ta có thể chọn **đỉnh khó tô trước** để phát hiện xung đột sớm. Một chiến lược thông dụng là **DSATUR** (*Degree of Saturation*).

Với một đỉnh **chưa tô** v, **độ bão hòa màu** là:

```text
saturation(v) =
    số lượng màu PHÂN BIỆT đã được dùng
    bởi những đỉnh kề v và đã tô.
```

Nếu v có ba hàng xóm đã tô màu [1,1,2] thì `saturation(v)=2`, **không phải 3**. Hai hàng xóm cùng màu chỉ chiếm một lựa chọn màu.

Trong mã Java:

1. Ưu tiên đỉnh chưa tô có **saturation lớn nhất**.
2. Nếu hòa saturation, ưu tiên **bậc (degree) lớn hơn**.
3. Nếu vẫn hòa, chọn **chỉ số đỉnh nhỏ hơn** để kết quả xác định.

**Degree** trong mã là số hàng xóm của v trong đồ thị gốc, không phải số hàng xóm chưa tô. Cả hai kiểu tie-break có thể dùng như heuristic, nhưng phải mô tả chính xác kiểu đang triển khai.

DSATUR có thể phát hiện những đỉnh bị giới hạn màu trước và rút ngắn số lần thử. Trong đồ thị tam giác với k=2, khi hai đỉnh kề nhau đã nhận hai màu khác nhau, đỉnh thứ ba sẽ không còn màu. Chọn nó sớm cho phép kết luận nhánh ấy thất bại ngay.

### DSATUR có phải thuật toán tham lam luôn tối ưu không?

**Không** nếu chỉ tô mỗi đỉnh bằng màu đầu tiên phù hợp rồi không quay lui. Cách tô tham lam theo thứ tự DSATUR là một heuristic, có thể dùng nhiều màu hơn sắc số hoặc thất bại với giới hạn k dù có nghiệm.

Chương trình dưới đây dùng DSATUR **chỉ để chọn đỉnh tiếp theo**, nhưng vẫn **thử mọi màu hợp lệ và quay lui**. Vì không loại bỏ tùy tiện nhánh nào, tính đầy đủ của tìm kiếm vẫn được giữ.

**Quan hệ với MRV:** MRV (*minimum remaining values*) chọn biến có ít giá trị còn hợp lệ nhất. Với mọi đỉnh đều có cùng tập màu 1..k và không có danh sách màu riêng, số màu còn lại của đỉnh đang chưa tô là `k−saturation(v)`. Do đó ưu tiên saturation lớn nhất tương đương ưu tiên ít màu khả dụng nhất trong mô hình cơ bản. Khi các đỉnh có danh sách màu riêng hoặc ràng buộc bổ sung, MRV và DSATUR không còn nhất thiết tương đương.

## 8. Cắt tỉa an toàn bằng forward checking

Sau khi tạm gán một màu, ta có thể kiểm tra các đỉnh chưa tô:

> Có đỉnh chưa tô nào mà **tất cả** màu từ 1..k đều đã bị hàng xóm đã tô chặn hay không?

Nếu có, không có cách nào hoàn thiện phép tô hiện tại, vì tô thêm các đỉnh khác **không thể làm mất những xung đột với các đỉnh đã cố định màu**. Như vậy có thể cắt ngay nhánh này.

```text
FORWARD-CHECK:
    for every uncolored vertex v:
        exists = false
        for c = 1..k:
            if SAFE(v,c):
                exists = true
                break
        if not exists:
            return false
    return true
```

**Forward checking là điều kiện cần, không phải điều kiện đủ.** Mỗi đỉnh có ít nhất một màu còn có thể dùng **không bảo đảm** các đỉnh chưa tô dùng được các màu ấy cùng lúc. Ví dụ tam giác k=2 khi chưa tô đỉnh nào: mỗi đỉnh đều có 2 màu có thể chọn, nhưng đồ thị vẫn không thể 2-colorable.

Vì vậy khi forward checking trả true, thuật toán **vẫn phải tiếp tục quay lui**. Chỉ được kết luận thất bại khi forward checking trả false; không được kết luận đã giải xong từ việc các miền màu đều khác rỗng.

**Chi phí bổ sung:** Quét mọi đỉnh chưa tô và thử màu tăng chi phí mỗi nút tìm kiếm. Với đồ thị khó, nó có thể giảm số nhánh đủ nhiều để có lợi, nhưng không đảm bảo **luôn nhanh hơn** so với quay lui thường. Trong bài học này, forward checking chỉ bật ở chế độ DSATUR để so sánh hai cách giải.

## 9. Minh họa DSATUR trên đường đi bốn đỉnh

Đồ thị có các cạnh (0,2), (1,3), (2,3), k=2.

Bậc các đỉnh:

```text
degree(0)=1
degree(1)=1
degree(2)=2
degree(3)=2
```

Ban đầu saturation mọi đỉnh bằng 0. DSATUR chọn đỉnh 2 vì degree=2 và chỉ số 2 nhỏ hơn 3.

- **Đỉnh 2:** màu 1.
- **Đỉnh 0:** kề đỉnh 2 màu 1, saturation=1. Đỉnh 3 cũng saturation=1 nhưng degree=2 lớn hơn degree của 0, vì vậy **DSATUR chọn đỉnh 3 trước**, gán màu 2.
- **Đỉnh 0:** kề đỉnh 2 màu 1, saturation=1, gán màu 2.
- **Đỉnh 1:** kề đỉnh 3 màu 2, gán màu 1.

Kết quả theo thứ tự đỉnh 0..3:

```text
[2, 1, 1, 2]
```

Tô màu hợp lệ và **không cần quay lui** trong nhánh này. Cách theo thứ tự 0..3 vẫn đúng nhưng cần thử lại màu của đỉnh 1; khác biệt là **hiệu quả tìm kiếm**, không phải **khả năng giải bài toán**.

### Truy vết đếm số lần quay lui

Để dễ quan sát, chương trình giữ hai bộ đếm:

- `attempts`: số lần gán tạm một màu **đã vượt qua kiểm tra SAFE**.
- `backtracks`: số lần một phép gán tạm không dẫn tới nghiệm và phải **đặt màu về 0**.
- `calls`: số lời gọi thủ tục đệ quy, gồm cả lần gọi tại trạng thái đã tô xong.

Với đường đi trên:

```text
Thứ tự cố định: 2 lần hoàn tác trước khi tìm được nghiệm.
DSATUR + forward checking: 0 lần hoàn tác.
```

Số lần quay lui **phụ thuộc thứ tự đỉnh, thứ tự màu và cắt tỉa**. Nó không phải bất biến toán học của đồ thị và không nên dùng nó để đánh giá tính đúng, chỉ để so sánh hiệu quả trong một triển khai đã xác định.

## 10. Chứng minh tính đúng của quay lui tô màu

### 10.1. Bất biến: mọi phép gán từng phần được giữ đều hợp lệ

Ban đầu tất cả đỉnh chưa tô, không có cạnh nối hai đỉnh đã tô cùng màu, nên bất biến đúng.

Giả sử bất biến đúng trước khi tô v. Hàm `SAFE(v,c)` chỉ trả true khi **mọi hàng xóm đã tô** của v có màu khác c. Do đó sau khi gán color[v]=c, mọi cạnh giữa hai đỉnh đã tô vẫn hợp lệ: cạnh không liên quan v giữ nguyên, cạnh liên quan v được kiểm tra.

Nếu nhánh thất bại, đặt color[v]=0 để khôi phục trạng thái của cấp gọi. Như vậy bất biến được duy trì trong toàn bộ quá trình.

Khi tất cả đỉnh đã tô, mọi cạnh có **hai đầu đã tô** và đều đã được kiểm tra khi đầu thứ hai nhận màu. Do đó mảng được trả là một **phép tô màu hợp lệ**. Đây là chứng minh **soundness**: thuật toán không trả nghiệm sai.

### 10.2. Tính đầy đủ: không bỏ sót nghiệm

Cố định một phép tô màu hợp lệ giả định T của toàn đồ thị. Xét một trạng thái từng phần tương thích với T.

- Thuật toán chọn một đỉnh v chưa tô (theo thứ tự cố định hoặc DSATUR).
- Vì T là tô màu hợp lệ, màu T[v] không xung đột với những đỉnh đã tô theo T. Vậy T[v] là một trong các màu mà vòng lặp có thể thử.
- Khi chọn màu T[v], trạng thái mới vẫn tương thích với T. Thuật toán tiếp tục xét đệ quy.
- Theo quy nạp số đỉnh chưa tô, luôn có một chuỗi nhánh dẫn tới T.

Nếu forward checking loại một trạng thái, có một đỉnh chưa tô **không có màu nào** tương thích với các màu đã cố định. Do đó trạng thái ấy **không thể** nằm trên bất kỳ nghiệm hoàn chỉnh nào. Forward checking chỉ cắt những nhánh không có nghiệm, nên không phá tính đầy đủ.

Vì thế, nếu tồn tại tô màu hợp lệ trong k màu, thuật toán quay lui sẽ tìm được một nghiệm; nếu đã duyệt hết và trả thất bại thì không có nghiệm. Việc chọn đỉnh bằng DSATUR **không ảnh hưởng chứng minh** vì vẫn chọn đúng một đỉnh chưa tô và thử đầy đủ mọi màu hợp lệ.

### 10.3. Thuật toán kết thúc

Mỗi lần đệ quy đi sâu đều **tô thêm đúng một đỉnh**, nên số đỉnh chưa tô giảm nghiêm ngặt. Độ sâu đệ quy tối đa n. Ở mỗi mức, số màu phải thử hữu hạn (tối đa k hoặc min(k,n)). Sau khi nhánh trả về, thuật toán hoàn tác hoặc kết thúc; do đó không có chu trình vô hạn trong cây tìm kiếm.

### 10.4. Đúng với đồ thị nhiều thành phần

Các đỉnh ở những thành phần liên thông khác nhau **không có cạnh nối nhau**, nên có thể dùng lại cùng tên màu. Thuật toán áp dụng cho toàn mảng màu và tất cả cạnh; không yêu cầu đồ thị liên thông.

Nếu xử lý riêng từng thành phần, mỗi thành phần có thể được tô tối đa k màu. Ghép các phép tô thành phần bằng cùng tập nhãn 1..k vẫn hợp lệ vì không có cạnh giữa các thành phần. Cách chia thành phần có thể tiết kiệm thời gian nếu các thành phần nhỏ.

## 11. Độ phức tạp và giới hạn của giải pháp

Gọi n=|V|, m=|E|, K=min(k,n) khi n>0.

### Quay lui theo thứ tự cố định

- Dựng ma trận kề: O(n²+m) thời gian/bộ nhớ khởi tạo theo kích thước ma trận; riêng ma trận tốn O(n²) bộ nhớ.
- Ở mỗi đỉnh, thử tối đa K màu; kiểm tra một màu bằng cách quét n đỉnh lân cận, tốn O(n).
- Cây tìm kiếm có thể chứa tới `1+K+K²+...+K^n` trạng thái gán từng phần (cận thô khi không có cắt nhánh).

Với K≥2, thường biểu diễn cận thời gian là **O(n·K^(n+1))** nếu đếm K phép thử màu tại mỗi nút, và các phép kiểm tra O(n); có thể đưa ra một cận an toàn, dễ nhớ hơn là **O(n²·(K+1)^n)** cho mọi K≥1. Trong diễn giải phổ thông, đây là **thời gian mũ theo n**, thường được nói gọn O(K^n) nếu coi chi phí kiểm tra tính hợp lệ là hằng số hoặc bỏ qua thừa số đa thức.

Với K=1, cây tìm kiếm không phân nhánh theo màu nhưng vẫn phải quét kiểm tra cạnh; cách viết `O(K^n)=O(1)` **không phản ánh chi phí thật**. Phải cộng các bước xử lý/kiểm tra dữ liệu.

### DSATUR và forward checking

Mỗi nút tìm kiếm còn phải:

1. Chọn đỉnh chưa tô theo saturation và degree; với ma trận kề, có thể cần O(n²+nK) thao tác để quét ứng viên và các màu hàng xóm.
2. Thử các màu; mỗi phép SAFE tốn O(n).
3. Sau gán, forward checking có thể thử tới n đỉnh × K màu × O(n) hàng xóm = O(n²K).

Vậy chi phí mỗi nút có cận trên **O(n²K)**, và vẫn có số nút tăng theo hàm mũ trong trường hợp xấu. DSATUR/forward checking thường giúp giảm **số nút thực tế**, không thay thế chứng minh độ phức tạp xấu nhất.

**Bộ nhớ:** Ma trận kề O(n²), màu/degree O(n), bộ đếm O(1), ngăn xếp đệ quy O(n), vùng tạm tính saturation O(K). Tổng **O(n²+n+K)**, thực tế O(n²) cho n≥1 và K≤n. Nếu dùng danh sách kề, việc kiểm tra màu và đếm saturation có thể tiết kiệm trên đồ thị thưa, nhưng phải tính lại chi phí theo bậc đỉnh.

### Độ khó tính toán

Bài quyết định liệu đồ thị có tô được bằng **3 màu** là bài toán **NP-complete** trong trường hợp tổng quát. Với số màu cố định k≥3, vấn đề k-colorability cũng là NP-complete theo nghĩa tổng quát (trừ trường hợp có cấu trúc đặc biệt). Điều này giải thích vì sao thuật toán quay lui có thể bùng nổ trên đồ thị lớn.

Những trường hợp đơn giản hơn:

- **k=0:** Chỉ đồ thị không có đỉnh mới có nghiệm trong quy ước 0 màu.
- **k=1:** Với đồ thị đơn n>0, có nghiệm **khi và chỉ khi không có cạnh**.
- **k=2:** Có nghiệm **khi và chỉ khi đồ thị hai phía** (*bipartite*). Kiểm tra bằng BFS/DFS trong **O(n+m)** nếu có danh sách kề.
- **k≥n:** Mọi đồ thị vô hướng đơn n đỉnh đều có nghiệm, vì mỗi đỉnh có thể nhận một màu riêng.
- **Đồ thị đầy đủ K_t:** Cần ít nhất t màu.
- **Chu trình chẵn:** 2 màu đủ; **chu trình lẻ:** ít nhất 3 màu.

Bởi vậy nên xử lý các trường hợp dễ bằng thuật toán chuyên biệt nếu cần hiệu năng, thay vì luôn dùng quay lui.

## 12. Chương trình Java 17+ hoàn chỉnh

Mã có hai chế độ:

- `Mode.ORDER`: quay lui theo **chỉ số đỉnh tăng dần**, dễ theo dõi và làm chuẩn đối chiếu.
- `Mode.DSATUR`: chọn đỉnh theo **saturation lớn nhất**, hòa thì degree lớn nhất, rồi chỉ số nhỏ nhất; sau mỗi gán còn chạy **forward checking** để cắt những nhánh đã mất mọi lựa chọn màu.

Cả hai trả `Result(possible, colors, calls, attempts, backtracks)`. Không có nghiệm thì `possible=false` và `colors=[]`; đồ thị rỗng n=0 có nghiệm `possible=true` và cũng có `colors=[]`. Vì vậy **không thể chỉ nhìn vào mảng rỗng để phân biệt hai trường hợp**, phải xem cờ possible.

Đầu vào là danh sách cạnh vô hướng. Chương trình xây ma trận kề, từ chối chỉ số đỉnh ngoài [0,n−1], cặp cạnh không hợp lệ, khuyên và tham số âm. Mỗi cạnh trùng không thay đổi đồ thị. Số màu thử thực tế được chặn bởi min(k,n) để tránh tạo bảng màu khổng lồ trong các đầu vào k≫n.

Lưu thành tệp **`BoundedGraphColoringDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

public class BoundedGraphColoringDemo {
    enum Mode { ORDER, DSATUR }

    record Result(boolean possible, int[] colors,
                  long calls, long attempts, long backtracks) {}

    private static final class Stats {
        long calls;
        long attempts;
        long backtracks;
    }

    static Result solve(int vertexCount, int[][] edges,
                        int maxColors, Mode mode) {
        if (vertexCount < 0) {
            throw new IllegalArgumentException(
                    "vertexCount must be nonnegative");
        }
        if (maxColors < 0) {
            throw new IllegalArgumentException(
                    "maxColors must be nonnegative");
        }
        Objects.requireNonNull(edges, "edges must not be null");
        Objects.requireNonNull(mode, "mode must not be null");

        int n = vertexCount;
        boolean[][] adjacent = new boolean[n][n];
        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException(
                        "each edge must have two endpoints");
            }
            int a = edge[0];
            int b = edge[1];
            if (a < 0 || a >= n || b < 0 || b >= n) {
                throw new IllegalArgumentException(
                        "vertex index out of range");
            }
            if (a == b) {
                throw new IllegalArgumentException(
                        "self-loops are not allowed");
            }
            adjacent[a][b] = true;
            adjacent[b][a] = true;
        }

        int[] degree = new int[n];
        for (int v = 0; v < n; v++) {
            for (int u = 0; u < n; u++) {
                if (adjacent[v][u]) {
                    degree[v]++;
                }
            }
        }

        if (n == 0) {
            return new Result(true, new int[0], 0, 0, 0);
        }
        if (maxColors == 0) {
            return new Result(false, new int[0], 0, 0, 0);
        }

        // n mau luon du voi do thi vo huong don.
        int palette = Math.min(maxColors, n);
        int[] colors = new int[n]; // 0 = chua to
        Stats stats = new Stats();

        boolean possible = backtrack(
                adjacent, degree, colors, palette, mode, stats);

        return new Result(
                possible,
                possible ? colors.clone() : new int[0],
                stats.calls, stats.attempts, stats.backtracks);
    }

    private static boolean safe(
            boolean[][] adjacent, int[] colors,
            int vertex, int candidate) {
        for (int u = 0; u < colors.length; u++) {
            if (adjacent[vertex][u]
                    && colors[u] == candidate) {
                return false;
            }
        }
        return true;
    }

    private static int chooseVertex(
            boolean[][] adjacent, int[] degree,
            int[] colors, int palette, Mode mode) {
        if (mode == Mode.ORDER) {
            for (int v = 0; v < colors.length; v++) {
                if (colors[v] == 0) {
                    return v;
                }
            }
            return -1;
        }

        int choice = -1;
        int bestSaturation = -1;
        int bestDegree = -1;

        // Tai moi lan goi, dung lai vung tam danh dau
        // cac mau phan biet quanh tung dinh.
        boolean[] seenColor = new boolean[palette + 1];

        for (int v = 0; v < colors.length; v++) {
            if (colors[v] != 0) {
                continue;
            }
            Arrays.fill(seenColor, false);
            int saturation = 0;

            for (int u = 0; u < colors.length; u++) {
                int c = colors[u];
                if (adjacent[v][u] && c != 0
                        && !seenColor[c]) {
                    seenColor[c] = true;
                    saturation++;
                }
            }

            // Duyet v tang: neu hoa ca hai,
            // giu nguyen dinh co chi so nho hon.
            if (saturation > bestSaturation
                    || (saturation == bestSaturation
                        && degree[v] > bestDegree)) {
                choice = v;
                bestSaturation = saturation;
                bestDegree = degree[v];
            }
        }
        return choice;
    }

    private static boolean forwardPossible(
            boolean[][] adjacent,
            int[] colors, int palette) {
        for (int v = 0; v < colors.length; v++) {
            if (colors[v] != 0) {
                continue;
            }
            boolean hasChoice = false;

            for (int c = 1; c <= palette; c++) {
                if (safe(adjacent, colors, v, c)) {
                    hasChoice = true;
                    break;
                }
            }
            if (!hasChoice) {
                return false;
            }
        }
        return true;
    }

    private static boolean backtrack(
            boolean[][] adjacent, int[] degree,
            int[] colors, int palette, Mode mode,
            Stats stats) {
        stats.calls++;
        int vertex = chooseVertex(
                adjacent, degree, colors, palette, mode);

        if (vertex == -1) {
            return true; // tat ca dinh da duoc to
        }

        for (int c = 1; c <= palette; c++) {
            if (!safe(adjacent, colors, vertex, c)) {
                continue;
            }

            stats.attempts++;
            colors[vertex] = c;

            boolean worthExploring =
                    mode == Mode.ORDER
                    || forwardPossible(adjacent, colors, palette);

            if (worthExploring
                    && backtrack(adjacent, degree, colors,
                                 palette, mode, stats)) {
                return true;
            }

            colors[vertex] = 0; // hoan tac bat buoc
            stats.backtracks++;
        }
        return false;
    }

    private static boolean validAnswer(
            int n, int[][] edges, int k, Result answer) {
        if (!answer.possible()) {
            return answer.colors().length == 0;
        }
        if (answer.colors().length != n) {
            return false;
        }
        for (int c : answer.colors()) {
            if (c < 1 || c > k) {
                return false;
            }
        }
        for (int[] e : edges) {
            if (answer.colors()[e[0]]
                    == answer.colors()[e[1]]) {
                return false;
            }
        }
        return true;
    }

    static void show(
            String label, int n, int[][] edges, int k) {
        Result ordered = solve(n, edges, k, Mode.ORDER);
        Result heuristic = solve(n, edges, k, Mode.DSATUR);

        if (ordered.possible() != heuristic.possible()
                || !validAnswer(n, edges, k, ordered)
                || !validAnswer(n, edges, k, heuristic)) {
            throw new AssertionError(
                    "solvers disagree or invalid coloring");
        }

        System.out.println(label + " (k=" + k + ")"
                + ": possible=" + heuristic.possible()
                + ", colors=" + Arrays.toString(heuristic.colors())
                + ", backtracks=" + ordered.backtracks()
                + "->" + heuristic.backtracks());
    }

    public static void main(String[] args) {
        int[][] triangle = {{0, 1}, {1, 2}, {2, 0}};
        int[][] square = {
            {0, 1}, {1, 2}, {2, 3}, {3, 0}
        };
        int[][] oddCycle = {
            {0, 1}, {1, 2}, {2, 3}, {3, 4}, {4, 0}
        };
        int[][] clique4 = {
            {0, 1}, {0, 2}, {0, 3},
            {1, 2}, {1, 3}, {2, 3}
        };
        int[][] trickyPath = {
            {0, 2}, {1, 3}, {2, 3}
        };

        show("Triangle", 3, triangle, 2);
        show("Triangle", 3, triangle, 3);
        show("Square", 4, square, 2);
        show("Odd cycle", 5, oddCycle, 2);
        show("Odd cycle", 5, oddCycle, 3);
        show("Clique K4", 4, clique4, 3);
        show("Clique K4", 4, clique4, 4);
        show("Disconnected", 5,
                new int[][]{{0, 1}, {2, 3}}, 2);
        show("Edgeless", 3, new int[0][], 1);
        show("Empty", 0, new int[0][], 0);
        show("No colors", 1, new int[0][], 0);
        show("Tricky path", 4, trickyPath, 2);

        try {
            solve(1, new int[][]{{0, 0}}, 2, Mode.ORDER);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid loop: " + ex.getMessage());
        }

        try {
            solve(2, new int[][]{{0, 2}}, 2, Mode.ORDER);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid vertex: " + ex.getMessage());
        }

        try {
            solve(2, new int[][]{{0}}, 2, Mode.ORDER);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid edge: " + ex.getMessage());
        }

        try {
            solve(1, new int[0][], -1, Mode.ORDER);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid k: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac BoundedGraphColoringDemo.java
java BoundedGraphColoringDemo
```

**Stdout chính xác:**

```text
Triangle (k=2): possible=false, colors=[], backtracks=4->4
Triangle (k=3): possible=true, colors=[1, 2, 3], backtracks=0->0
Square (k=2): possible=true, colors=[1, 2, 1, 2], backtracks=0->0
Odd cycle (k=2): possible=false, colors=[], backtracks=8->8
Odd cycle (k=3): possible=true, colors=[1, 2, 1, 2, 3], backtracks=0->0
Clique K4 (k=3): possible=false, colors=[], backtracks=15->15
Clique K4 (k=4): possible=true, colors=[1, 2, 3, 4], backtracks=0->0
Disconnected (k=2): possible=true, colors=[1, 2, 1, 2, 1], backtracks=0->0
Edgeless (k=1): possible=true, colors=[1, 1, 1], backtracks=0->0
Empty (k=0): possible=true, colors=[], backtracks=0->0
No colors (k=0): possible=false, colors=[], backtracks=0->0
Tricky path (k=2): possible=true, colors=[2, 1, 1, 2], backtracks=2->0
Invalid loop: self-loops are not allowed
Invalid vertex: vertex index out of range
Invalid edge: each edge must have two endpoints
Invalid k: maxColors must be nonnegative
```

### Giải thích đầu ra

- **Triangle k=2:** Không có nghiệm; cả hai bộ giải phải đi qua các nhánh khả thi và hoàn tác trước khi kết luận.
- **Triangle k=3:** Ba đỉnh đôi một kề nhau cần ba màu, mảng [1,2,3] hợp lệ.
- **Square k=2:** Chu trình chẵn, tô xen kẽ 1,2 là đủ.
- **Odd cycle k=2:** Chu trình lẻ không hai phía; quay lui không tìm được nghiệm. Với k=3, có thể tô bốn đỉnh đầu xen kẽ và đỉnh cuối màu 3.
- **Clique K4:** Bốn đỉnh đôi một kề nhau cần bốn màu; k=3 không thể, k=4 có nghiệm.
- **Disconnected:** Các thành phần riêng biệt được phép tái sử dụng màu 1,2; đỉnh cô lập có thể nhận màu 1.
- **Edgeless:** Không có cạnh nên một màu đủ cho tất cả các đỉnh.
- **Empty:** Không có đỉnh thì mảng rỗng là nghiệm hợp lệ với k=0.
- **No colors:** Có đỉnh nhưng k=0, không có giá trị màu hợp lệ nào.
- **Tricky path:** Bản theo thứ tự cố định phải **quay lui 2 lần**, trong khi DSATUR chọn đỉnh bậc lớn trước và tìm nghiệm mà không phải hoàn tác.
- **Invalid:** Self-loop, đỉnh ngoài miền, cạnh không đúng cặp và k âm được kiểm tra rõ. Nếu muốn coi self-loop là một bài không có nghiệm thay vì đầu vào không hợp lệ, có thể điều chỉnh API; không được âm thầm tô nó.

### Vì sao hai bản có thể trả hai mảng khác nhau?

Một đồ thị có nhiều phép tô hợp lệ. Bản ORDER gán đỉnh theo chỉ số; bản DSATUR chọn đỉnh theo mức độ bão hòa màu, nên thứ tự ra quyết định khác. Cả hai đều kiểm tra cùng ràng buộc và giới hạn k, nên **chỉ cần cùng kết luận khả thi/không khả thi và mỗi mảng màu được trả đều hợp lệ**; không bắt buộc các mảng bằng nhau.

Trong `show`, hàm `validAnswer` kiểm tra độ dài mảng, miền màu và mọi cạnh đầu vào. Phép đối chiếu này là kiểm thử triển khai hữu ích, nhưng **không thay thế chứng minh toán học** cho mọi đồ thị.

### Tại sao phải kiểm tra mode và null?

Mã từ chối `null` cho danh sách cạnh và Mode, không tự chọn chiến lược mặc định vô thức. Với mảng đầu vào được giữ cố định trong quá trình gọi, bản ORDER và DSATUR luôn thực thi cùng một đồ thị. Nếu gọi API với `null` hoặc cạnh có độ dài khác 2, ngoại lệ sẽ mô tả lỗi hợp đồng thay vì gây truy cập mảng ngoài miền một cách khó hiểu.

## 13. Có thể tối ưu tiếp những gì?

### 13.1. Dùng danh sách kề trên đồ thị thưa

Trong code mẫu, `boolean[n][n]` giúp hàm SAFE xét nhanh sự tồn tại cạnh nhưng tốn O(n²) bộ nhớ. Nếu n lớn, m nhỏ, danh sách kề `List<Integer>[]` thường phù hợp hơn:

- Kiểm tra một màu ở v chỉ cần duyệt hàng xóm của v, O(degree(v)).
- Tính bậc từ độ dài danh sách kề.
- DSATUR chỉ cần xét màu ở các hàng xóm thực sự.

Nhưng danh sách kề với cạnh trùng phải được xử lý nếu đếm degree/saturation theo số đỉnh kề **phân biệt**; việc nhập cạnh trùng hai lần có thể khiến bậc bị đếm sai nếu không chuẩn hóa.

### 13.2. Kiểm tra cận dưới về số màu

Nếu đồ thị chứa một **clique** kích thước t, cần ít nhất t màu. Phát hiện một clique có t>k cho phép kết luận **không có nghiệm** ngay. Tuy vậy tìm clique lớn nhất là bài khó trong trường hợp tổng quát; chỉ cần tìm một clique đủ lớn để làm chứng cứ cắt, không nên coi việc tính cận dưới là miễn phí.

Một **clique K4** đòi bốn màu; đây là chứng cứ trực tiếp vì bốn đỉnh đều kề nhau và không được chia sẻ màu.

### 13.3. Phá đối xứng màu

Tên các màu 1..k có thể hoán đổi cho nhau mà không thay đổi tính hợp lệ. Một tối ưu thường dùng là quy ước màu mới phải là **màu nhỏ nhất chưa dùng**, hoặc chỉ cho phép dùng màu từ 1 đến số màu đã dùng+1. Cách phá đối xứng có thể giảm rất nhiều nhánh lặp.

**Tuy nhiên:** Phải chứng minh quy tắc phá đối xứng không loại hết những hoán vị đại diện của một nghiệm hợp lệ. Trong chương trình mẫu, để giữ cách tìm kiếm dễ kiểm chứng, ta **không áp dụng** cắt tỉa loại đối xứng này.

### 13.4. Giải riêng từng thành phần liên thông

Nếu đồ thị có nhiều thành phần, một tô màu chung k màu tồn tại khi và chỉ khi **mỗi thành phần** đều k-colorable. Có thể xử lý từng thành phần, dùng lại nhãn màu từ 1 đến k; không cần dùng các màu mới cho thành phần sau.

Cách này có thể làm giảm độ khó thực tế so với xây cây tìm kiếm trên toàn đồ thị nếu có nhiều thành phần nhỏ.

### 13.5. Chọn biến theo MRV, bậc, hoặc mức ràng buộc

DSATUR là một dạng chọn đỉnh ít màu còn lại trong mô hình tất cả đỉnh có cùng bảng màu; các biến thể có thể ưu tiên degree của **các đỉnh chưa tô** khi hòa, hoặc chọn đỉnh tác động mạnh nhất tới những đỉnh còn lại (*most constraining variable*).

Những lựa chọn này là heuristic về **thứ tự**, không phải các điều kiện cần của tính đúng. Một heuristic tốt trên loại đồ thị này có thể không tốt trên loại khác; cần đo số nút tìm kiếm và chi phí mỗi nút.

### 13.6. Các bài toán khó hơn cần trạng thái khác

Nếu mỗi đỉnh v chỉ được chọn trong danh sách màu riêng `allowed[v]`, biến “miền màu còn lại” không chỉ phụ thuộc saturation. Chuyển trạng thái phải thử **đúng màu được phép**.

Nếu vài đỉnh đã có màu **cố định**, không được quay lui thay màu của chúng; phải kiểm tra xung đột ban đầu và chỉ chọn đỉnh chưa khóa.

Nếu muốn **tối thiểu số màu**, có thể chạy bộ giải k-coloring nhiều lần với k giảm/tăng và dùng cận; hoặc dùng một thuật toán nhánh cận xây dựng sắc số trực tiếp. Không được nhầm kết luận “có nghiệm với k=4” thành “sắc số bằng 4”.

## 14. Các lỗi phổ biến

1. **Gán màu mà không kiểm tra hàng xóm đã tô.** Có thể tạo cạnh có hai đầu cùng màu và trả lời sai.
2. **Quên khôi phục color[v]=0 sau nhánh thất bại.** Màu còn sót làm hỏng các nhánh sau.
3. **Chỉ thử một màu đầu tiên, không quay lui.** Khi gặp ngõ cụt, không được suy ra đồ thị không tô được k màu.
4. **Nhầm “tối đa k” với “phải dùng đúng k”.** Đây là hai yêu cầu khác nhau.
5. **Coi 0 là màu thứ nhất.** Trong code, 0 biểu diễn chưa tô; màu hợp lệ là 1..k.
6. **Không xử lý n=0.** Đồ thị rỗng có nghiệm rỗng với k=0.
7. **Không xử lý n>0, k=0.** Không có màu để gán, nên không có nghiệm.
8. **Bỏ qua self-loop.** Nếu có cạnh {v,v}, điều kiện color[v] != color[v] là bất khả thi; mã chọn từ chối input.
9. **Dùng thuật toán cho đồ thị vô hướng lên đồ thị có hướng mà không định nghĩa lại xung đột.**
10. **Đếm màu ở hàng xóm thay vì màu phân biệt.** DSATUR phải đếm số **màu khác nhau** đã dùng quanh v.
11. **Nhầm độ bão hòa với bậc đỉnh.** Degree là số hàng xóm; saturation là số màu phân biệt đang xuất hiện ở hàng xóm đã tô.
12. **Coi DSATUR greedy là chứng minh có nghiệm.** DSATUR nếu không quay lui vẫn có thể thất bại dù tồn tại nghiệm.
13. **Dùng forward checking như một điều kiện đủ.** Các miền màu đều không rỗng không có nghĩa các đỉnh chưa tô tương thích lẫn nhau.
14. **Cắt nhánh vì “không thấy lựa chọn tốt” nhưng chưa chứng minh không có nghiệm.** Cắt sai phá tính đầy đủ.
15. **Chỉ kiểm tra cạnh giữa hai đỉnh liên tiếp theo chỉ số.** Cạnh có thể nối bất kỳ cặp nào.
16. **Bỏ mất một chiều của cạnh vô hướng khi xây đồ thị.** Trong mã mẫu, mỗi cạnh gán cả adj[u][v] và adj[v][u].
17. **Coi hai đỉnh không có cạnh cũng phải khác màu.** Chúng được dùng lại màu.
18. **Không tô các đỉnh cô lập.** Dù không có cạnh, mỗi đỉnh vẫn phải nhận một màu nếu n>0.
19. **Không xử lý cạnh trùng.** Danh sách kề có thể đếm bậc sai nếu không chuẩn hóa; ma trận kề tự gộp.
20. **Trả colors=[] mà không có possible.** Mảng rỗng vừa là nghiệm của n=0, vừa là cách biểu diễn không có nghiệm; cần cờ riêng.
21. **Nói “mọi đồ thị có k=2 đều cần backtracking”.** Bài 2-colorability có lời giải tuyến tính bằng BFS/DFS.
22. **Dùng k màu trong cấp phát mà không xét k rất lớn.** Với k>n, có thể giới hạn số màu thực tế tại n cho đồ thị đơn.
23. **Khẳng định DSATUR luôn giảm số backtracks.** Heuristic có chi phí và phụ thuộc hình dạng đồ thị; không có bảo đảm cải thiện ở mọi input.
24. **Không lưu điều kiện kết thúc.** Chỉ trả true khi **mọi đỉnh** đã được tô.
25. **Thử các màu ngoài miền 1..k.** Một lời giải dùng k+1 màu không trả lời bài k-colorability.
26. **Nhầm tô màu đỉnh với tô màu cạnh.** Đối tượng cần khác màu trong hai bài khác nhau.
27. **Khẳng định chi phí đa thức cho k≥3 tổng quát.** Bài k-colorability với k cố định ≥3 là NP-complete; quay lui vẫn có cận mũ.
28. **Tìm số sắc bằng một lần chạy k.** Kết quả với một k chỉ cho biết `χ(G)≤k` hay `χ(G)>k`, không trực tiếp cho giá trị χ.
29. **Không kiểm chứng mảng kết quả.** Dù search trả true, nên kiểm tra số đỉnh, miền màu và mọi cạnh ở bài test.
30. **Không ghi rõ quy tắc hòa DSATUR.** Các cách chọn đỉnh hòa có thể cho mảng kết quả và số lần quay lui khác nhau, khiến stdout không tái lập.
31. **Không phân biệt bất khả thi với đầu vào sai.** Mã nêu rõ self-loop không thuộc đồ thị đơn, còn tam giác với k=2 là đồ thị hợp lệ nhưng không có nghiệm.
32. **Suy từ một nhánh fail rằng bài không có nghiệm.** Chỉ khi vòng màu đã hết ở cấp gốc và không còn nhánh hợp lệ mới kết luận bất khả thi.

## 15. Bài tập tự luyện có đáp án

**Bài 1.** Đồ thị tam giác có tô được bằng 2 màu không? Bằng 3 màu thì sao?

**Đáp án:** Không thể với 2 màu vì ba đỉnh đôi một kề nhau. Có thể với 3 màu, ví dụ [1,2,3].

**Bài 2.** Đồ thị chu trình bốn đỉnh (0,1),(1,2),(2,3),(3,0) với k=2 có nghiệm gì?

**Đáp án:** [1,2,1,2]. Hai đỉnh đối diện không kề nhau có thể dùng cùng màu.

**Bài 3.** Chu trình năm đỉnh có thể 2-colorable không?

**Đáp án:** Không. Đây là chu trình lẻ, không phải đồ thị hai phía. Cần ít nhất 3 màu; một tô màu hợp lệ là [1,2,1,2,3] nếu các cạnh nối liên tiếp quanh vòng.

**Bài 4.** Với đồ thị đường đi 0—2—3—1 và thứ tự gán 0,1,2,3, tại sao greedy màu nhỏ nhất có thể mắc kẹt?

**Đáp án:** Greedy cho 0=1,1=1,2=2, khiến 3 kề cả màu 1 và 2. Quay lui đổi màu của 1 thành 2, nhận [1,2,2,1], nên đồ thị vẫn 2-colorable.

**Bài 5.** DSATUR ưu tiên một đỉnh có ba hàng xóm mang màu [1,1,2] hay một đỉnh có hai hàng xóm mang màu [1,2]? Nếu degree khác nhau thì sao?

**Đáp án:** Cả hai có saturation=2, vì chỉ đếm **màu phân biệt**. Theo chính sách code, hòa saturation thì chọn đỉnh có **degree lớn hơn**, sau đó chỉ số nhỏ hơn.

**Bài 6.** Forward checking thấy một đỉnh chưa tô không còn màu nào tương thích. Có thể bỏ cả nhánh không?

**Đáp án:** Có. Không thể hoàn thành nhánh vì tô thêm các đỉnh khác không thể làm những xung đột hiện tại biến mất. Đây là cắt tỉa an toàn.

**Bài 7.** Forward checking thấy mọi đỉnh đều còn ít nhất một màu. Có thể tuyên bố tìm được nghiệm không?

**Đáp án:** Không. Các đỉnh chưa tô có thể cần cùng một màu nhưng lại kề nhau, nên các lựa chọn còn lại có thể xung đột. Vẫn phải tiếp tục quay lui.

**Bài 8.** Đồ thị K4 cần tối thiểu bao nhiêu màu?

**Đáp án:** Bốn. Mọi cặp đỉnh đều kề nhau nên không thể chia sẻ màu.

**Bài 9.** Đồ thị có n=0, k=0. Kết quả? Nếu n=1,k=0?

**Đáp án:** n=0 có nghiệm rỗng. n=1 nhưng k=0 thì không có màu hợp lệ cho đỉnh duy nhất, nên không có nghiệm.

**Bài 10.** Hai thành phần liên thông không có cạnh nối có được dùng lại cùng bộ màu không?

**Đáp án:** Được. Điều kiện chỉ cấm cùng màu ở **hai đầu của một cạnh**; không có cạnh giữa các thành phần nên dùng lại các màu là hợp lệ.

**Bài 11.** Nếu k=n+10 cho đồ thị đơn n đỉnh, cần duyệt đủ k màu cho mỗi đỉnh không?

**Đáp án:** Không. n màu đã đủ bằng cách gán màu khác nhau cho mọi đỉnh. Có thể dùng effectiveK=min(k,n) mà không làm mất nghiệm.

**Bài 12.** Trong mã, dấu hiệu nào cho biết thuật toán đã tô xong toàn bộ đồ thị?

**Đáp án:** Hàm chọn đỉnh trả −1, nghĩa là không còn đỉnh có color=0. Khi ấy mọi cạnh đều hợp lệ nhờ bất biến kiểm tra mỗi lần gán, nên trả true.

**Bài 13.** Vì sao phải đặt color[v]=0 khi lời gọi con trả false?

**Đáp án:** Đó là bước **hoàn tác** để cấp gọi trước có thể thử màu khác trên đúng trạng thái ban đầu. Không làm sẽ giữ những lựa chọn thuộc nhánh đã thất bại, gây kết quả sai.

**Bài 14.** Một tô màu hợp lệ dùng 2 màu và giới hạn k=4. Đồ thị có 4-colorable theo nghĩa “dùng tối đa 4 màu” không?

**Đáp án:** Có. Giới hạn là **tối đa**, không đòi dùng hết 4 màu.

**Bài 15.** Nếu chỉ cần kiểm tra k=2, nên dùng backtracking hay BFS/DFS để giải đồ thị lớn?

**Đáp án:** Nên dùng BFS/DFS kiểm tra **tính hai phía**, O(n+m), nhanh và dễ dự đoán hơn so với tìm kiếm quay lui tổng quát.

**Bài 16.** Cho một đồ thị có khuyên (2,2). Nó có phép tô màu đỉnh hợp lệ với một số màu hữu hạn không?

**Đáp án:** Không. Điều kiện color[2] != color[2] bất khả thi. Với hợp đồng **đồ thị đơn**, chương trình mẫu từ chối đầu vào có self-loop; trong mô hình đa đồ thị cho phép khuyên, có thể báo không có nghiệm.

**Bài 17.** Tại sao từ việc chạy `solve(k=3)` trả true không thể kết luận sắc số là 3?

**Đáp án:** Đồ thị có thể đã tô được bằng 1 hoặc 2 màu. Đáp án true chỉ chứng minh `χ(G)≤3`, không chứng minh `χ(G)=3`.

**Bài 18.** Nếu ở một trạng thái partial coloring, DSATUR chọn một đỉnh khác với thứ tự 0..n−1, liệu tính đúng có đổi?

**Đáp án:** Không, miễn là thuật toán vẫn chọn **một đỉnh chưa tô**, thử **mọi màu hợp lệ**, hoàn tác đúng và không cắt nhánh có thể chứa nghiệm. Heuristic đổi thứ tự duyệt, không loại nghiệm.

## Ghi nhớ

Bài toán **tô màu đồ thị bằng số màu giới hạn** hỏi có thể gán **tối đa k màu** cho mọi đỉnh của đồ thị vô hướng đơn sao cho hai đầu mỗi cạnh **khác màu** hay không. Quay lui đi từng đỉnh, thử màu 1..k, kiểm tra các hàng xóm đã tô, tiếp tục đệ quy và **hoàn tác color[v]=0** khi nhánh thất bại. Chứng minh đúng gồm **bất biến không xung đột**, **tính đầy đủ do thử mọi lựa chọn**, và **kết thúc vì số đỉnh chưa tô giảm**.

**DSATUR** ưu tiên đỉnh có **nhiều màu hàng xóm phân biệt nhất**, giúp phát hiện xung đột sớm; **forward checking** chỉ cắt nhánh khi một đỉnh chưa tô không còn màu nào. Đây là những tối ưu thực dụng, **không** phải phép thay thế việc thử đầy đủ các màu. Trong trường hợp xấu, bài vẫn có độ phức tạp **mũ** theo n; đặc biệt **k=2** nên dùng kiểm tra đồ thị hai phía O(n+m). Khi thấy một nhánh greedy thất bại, đừng kết luận đồ thị vô nghiệm: **quay lui và thử cách khác** mới là ý tưởng cốt lõi.

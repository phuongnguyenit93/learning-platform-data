# Phân rã trọng tâm cho truy vấn theo khoảng cách

**Phân rã trọng tâm (centroid decomposition)** là kỹ thuật chia một **cây** thành các phần cân bằng bằng cách lần lượt chọn một **trọng tâm** (centroid) của từng thành phần, loại bỏ trọng tâm ấy, rồi đệ quy trên các phần còn lại. Cấu trúc sinh ra là một **cây trọng tâm** (*centroid tree*) có chiều cao **O(log n)**, dù cây ban đầu có thể là một đường thẳng rất sâu.

Điểm mạnh của phân rã trọng tâm không phải chỉ để “chia cây”: nó cho phép biến những truy vấn phụ thuộc **khoảng cách trên cây gốc** thành một số nhỏ các thao tác trên **chuỗi trọng tâm tổ tiên** của mỗi đỉnh. Những bài điển hình là: bật/tắt trạng thái đánh dấu của một đỉnh, hỏi **khoảng cách đến đỉnh đang được đánh dấu gần nhất**, hoặc hỏi **có bao nhiêu đỉnh đang được đánh dấu nằm trong khoảng cách không quá k**. Với dữ liệu phù hợp, mỗi cập nhật/truy vấn không cần duyệt lại cả cây.

Bài thuộc nhóm **Thuật toán trên cây**, tập trung vào **Phân rã trọng tâm cho truy vấn theo khoảng cách**. Ta sẽ xây trọng tâm và cây trọng tâm; chứng minh độ sâu logarit; giải thích tính chất đường đi qua trọng tâm phân tách; xây hai loại truy vấn động, trong đó **truy vấn đếm cần cộng–trừ theo nhánh để tránh đếm trùng**; cài đặt **Java 17+ chạy độc lập** trên cây **không trọng số**, hỗ trợ bật/tắt đỉnh; phân tích thời gian–bộ nhớ, giới hạn áp dụng và kiểm thử bằng BFS vét cạn.

**Mục tiêu học tập:** tìm đúng centroid của từng thành phần hiện còn; xây chuỗi tổ tiên trọng tâm cho mỗi đỉnh cùng khoảng cách trong **cây gốc**; cập nhật một đỉnh theo các tổ tiên ấy; trả lời truy vấn gần nhất chính xác; áp dụng **inclusion–exclusion** để đếm đỉnh trong bán kính; hiểu tại sao các cấu trúc đa tập và Fenwick hỗ trợ xóa mà một biến “giá trị min” đơn thuần không làm được.

## 1. Định nghĩa bài toán khoảng cách trên cây

Cho cây vô hướng gồm **n≥1 đỉnh** đánh số `0..n−1`, có **đúng n−1 cạnh**, liên thông và không chu trình. Trong phiên bản cài đặt của bài, **mỗi cạnh có độ dài 1**. Vì vậy:

**`dist(u,v)` = số cạnh trên đường đi đơn duy nhất từ u tới v.**

Khoảng cách thỏa:

- `dist(u,u)=0`.
- `dist(u,v)=dist(v,u)`.
- Bất đẳng thức tam giác `dist(u,v)≤dist(u,c)+dist(c,v)`.
- Nếu c **nằm trên đường đi đơn** từ u tới v thì **`dist(u,v)=dist(u,c)+dist(c,v)`**.

Mỗi đỉnh v có trạng thái **active** (đang đánh dấu) hoặc **inactive**. Ban đầu, trong chương trình Java, **mọi đỉnh đều inactive**.

Ta muốn hỗ trợ:

1. **`toggle(v)`:** đổi trạng thái active/inactive của v. Bật rồi tắt phải hoàn tác đầy đủ đóng góp của v.
2. **`nearest(v)`:** trả **`min_{u active}dist(v,u)`**; nếu không có đỉnh active trả **−1** theo hợp đồng API.
3. **`countWithin(v,k)`:** trả số đỉnh active u với **`dist(v,u)≤k`**. Nếu k âm thì trả 0. Nếu chính v active, nó được tính trong bán kính 0.

Ví dụ với cây:

~~~text
       0
       |
       1 ----- 2
       |
       3 ----- 4
       |
       5 ----- 6
       |
       7
~~~

Danh sách cạnh là `(0,1),(1,2),(1,3),(3,4),(3,5),(5,6),(5,7)`; hình vẽ chỉ minh họa cấu trúc phân nhánh tại 1,3,5.

Nếu active={2,6} thì `dist(4,2)=3` và `dist(4,6)=3`, do đó `nearest(4)=3`; `countWithin(4,2)=0` và `countWithin(4,3)=2`.

### Vì sao BFS từng truy vấn chưa đủ?

Trên cây không trọng số, có thể dùng BFS từ đỉnh v rồi kiểm tra active. Cách này hoàn toàn đúng, nhưng mỗi lần hỏi có thể tốn **O(n)** thời gian; với q truy vấn, chi phí tới O(nq). Một cây hình đường thẳng có n rất lớn sẽ khiến nhiều truy vấn gần nhất hoặc đếm trong bán kính trở nên đắt.

Ta cần **tiền xử lý cấu trúc tĩnh** của cây, rồi cập nhật/truy vấn chỉ các mục dữ liệu liên quan đến những trọng tâm trên một chuỗi ngắn.

## 2. Centroid của một cây hoặc thành phần là gì?

Với một thành phần liên thông S của cây chứa m đỉnh, một đỉnh c gọi là **centroid** nếu sau khi **loại bỏ c cùng các cạnh kề c**, mỗi thành phần liên thông còn lại có kích thước **không quá `⌊m/2⌋`**.

Centroid **khác** trọng tâm trong hình học và **khác** tâm cây (*tree center*) theo bán kính/eccentricity. Hai khái niệm cũng không đồng nhất với “đỉnh có bậc cao nhất”.

**Ví dụ:** đường thẳng 7 đỉnh:

~~~text
0 -- 1 -- 2 -- 3 -- 4 -- 5 -- 6
~~~

Đỉnh 3 là centroid: bỏ 3 được hai phần có kích thước 3 và 3, không phần nào quá một nửa. Với đường thẳng 8 đỉnh, hai đỉnh giữa 3 hoặc 4 đều có thể là centroid; thuật toán chỉ cần chọn **một** centroid hợp lệ.

### Vì sao cây luôn có centroid?

Bắt đầu tại một đỉnh tùy ý. Nếu có một thành phần sau khi loại đỉnh đang xét chứa **hơn một nửa** số đỉnh, di chuyển sang người hàng xóm dẫn vào phần lớn ấy. Khi chuyển sang phía đó, “phần ngoài” phía sau có kích thước **nhỏ hơn một nửa**, nên không thể quay trở lại theo cùng lý do. Ta không thể di chuyển mãi trong cây hữu hạn, và cuối cùng đến đỉnh không có phần nào lớn hơn m/2 — chính là centroid.

Cũng có thể tính centroid bằng kích thước cây con trong một DFS:

- Chọn gốc tạm trong thành phần S.
- Tính `size[v]` là số đỉnh trong cây con của v (chỉ xét cạnh không đi qua những centroid đã loại).
- Sau khi bỏ v, thành phần “phía cha” có kích thước `m−size[v]`.
- Mỗi thành phần “phía con u” có kích thước `size[u]`.
- v là centroid khi **`max(m−size[v], max_child size[u])≤m/2`**.

Điều kiện kiểm tra **mọi phía**, gồm cả phía cha. Chọn đỉnh chỉ vì size[v] gần m/2 mà quên phần phía cha có thể sai.

## 3. Xây dựng cây trọng tâm (centroid tree)

Bắt đầu với toàn bộ cây gồm n đỉnh.

1. Chọn một centroid c của thành phần hiện tại.
2. Ghi c là gốc của phần cây trọng tâm tương ứng.
3. **Đánh dấu c đã bị loại khỏi các lần tìm centroid sau.**
4. Loại c khỏi thành phần, thu những thành phần nhỏ hơn tương ứng với các nhánh kề c.
5. Đệ quy xử lý từng thành phần ấy; centroid mới của mỗi phần sẽ là **con của c trong cây trọng tâm**.
6. Khi thành phần chỉ có một đỉnh, đỉnh ấy là centroid và không còn phần nào để chia.

Kết quả là một cây mới trên **chính n đỉnh gốc**, nhưng cạnh của **cây trọng tâm** nối centroid cha với centroid con, **không nhất thiết là cạnh có sẵn của cây gốc**.

### Tại sao chiều cao O(log n)?

Ở mỗi mức chia, centroid bảo đảm mọi phần còn lại có nhiều nhất một nửa số đỉnh của phần trước. Trên một chuỗi đi từ gốc cây trọng tâm xuống một đỉnh:

**`n, ≤n/2, ≤n/4, ≤n/8, ...`.**

Sau O(log n) lần chia, thành phần chỉ còn một đỉnh. Do đó:

- Mỗi đỉnh có **O(log n)** trọng tâm tổ tiên, kể cả chính nó.
- Mỗi thao tác cập nhật có thể đi qua O(log n) mức phân rã.
- Tổng số cặp “đỉnh gốc v — trọng tâm tổ tiên c” được lưu là **O(n log n)**.

**Không nhầm:** cây gốc có thể có chiều cao n nếu ta tự chọn gốc ở đầu đường thẳng; điều đó không làm mất bảo đảm O(log n) của cây **trọng tâm**.

### Phân rã chỉ đúng khi đầu vào là cây

Nếu đồ thị có chu trình, việc bỏ một đỉnh có thể không tạo các nhánh tách rời như cây; phép duyệt dựa vào một cạnh cha không đủ tránh revisiting. Nếu đầu vào là một rừng, cần xử lý riêng từng thành phần. Chương trình của bài yêu cầu **đúng một cây**, kiểm tra n−1 cạnh và không có chu trình; với các điều kiện ấy, liên thông được suy ra.

## 4. Dữ liệu tiền xử lý: tổ tiên trọng tâm và khoảng cách

Khi tách một thành phần ở centroid c, duyệt **các đỉnh đang thuộc thành phần** và lưu cho mỗi v:

**`Step(v,c)=(centroid=c, distance=dist_G(v,c), branch=b)`.**

Trong đó:

- `distance` là khoảng cách trong **cây gốc G**, không phải số bước trên cây trọng tâm.
- `branch` nhận dạng nhánh chứa v **sau khi bỏ centroid c**, thường lấy **đỉnh kề trực tiếp c** dẫn vào nhánh ấy.
- Nếu `v=c`, đặt `distance=0` và `branch=−1` vì không thuộc nhánh nào.

Khi phân rã đi tiếp xuống các thành phần con, mỗi v sẽ nhận thêm Step với centroid sâu hơn. Do đó `steps[v]` chứa các centroid tổ tiên của v từ trên xuống, **tối đa O(log n) mục**.

### Bất biến quan trọng của branch

Tại một centroid c, các đỉnh trong thành phần được phân rã tại c được chia thành:

- Chính c.
- Những nhánh khác nhau khi bỏ c.

Nếu u và v **nằm ở hai nhánh khác nhau**, hoặc một trong chúng là c, đường đi đơn u↔v trong cây gốc **bắt buộc đi qua c**, nên:

**`dist(u,v)=dist(u,c)+dist(c,v)`.**

Nếu u và v **nằm cùng một nhánh**, đường đi giữa chúng không cần đi qua c; lúc này tổng qua c **có thể lớn hơn khoảng cách thật**.

Đây là nền tảng của cả hai kiểu truy vấn:

- Truy vấn **gần nhất** có thể lấy min các đường đi “qua c”, vì ta có ít nhất một centroid đúng nằm trên đường nối cặp đỉnh tối ưu.
- Truy vấn **đếm trong bán kính** không thể cộng thẳng tất cả centroid, vì có thể **đếm trùng** hoặc đếm cả ứng viên mà đường qua c dài hơn đường thật. Phải **trừ nhánh chứa v** tại từng centroid.

### Các Step được tạo khi nào?

Ngay lúc chọn centroid c, ta chỉ cần DFS/BFS **trong thành phần còn hoạt động**, cộng khoảng cách từ c trên các cạnh gốc (mỗi cạnh độ dài 1). Ghi Step cho mọi đỉnh được duyệt.

Mã Java dùng **DFS với stack tường minh** khi đi qua một thành phần. Việc tìm centroid cũng dùng stack tường minh để tính thứ tự và subtree size; chỉ riêng các **lời gọi phân rã** mới dùng đệ quy, sâu O(log n). Cách này tránh stack DFS đệ quy có chiều sâu O(n) trên cây hình đường thẳng.

## 5. Truy vấn khoảng cách tới đỉnh active gần nhất

Ta cần hỗ trợ `toggle(v)` và `nearest(v)`. Với mỗi centroid c, duy trì **đa tập khoảng cách**:

**`D_c={dist(c,u) : u đang active và c là trọng tâm tổ tiên của u}`.**

Tức mỗi đỉnh active u đóng góp **một khoảng cách** vào mọi centroid c trên `steps[u]`.

### Vì sao phải dùng đa tập?

Hai đỉnh active có thể có cùng khoảng cách tới c. Nếu chỉ lưu `Set<Integer>`, khi tắt một đỉnh ở khoảng cách d ta có thể xóa cả giá trị d, dù vẫn còn đỉnh active khác cũng ở khoảng cách d.

Cài đặt an toàn là **`TreeMap<Integer,Integer>`**:

- Khóa = khoảng cách d.
- Giá trị = **số đỉnh active** đang đóng góp khoảng cách d.
- Khi bật u: cộng 1 vào tần suất d trên mọi centroid tổ tiên.
- Khi tắt u: trừ 1; chỉ xóa khóa khi tần suất về 0.
- Nếu map không rỗng, `firstKey()` cho **khoảng cách nhỏ nhất** tới centroid c trong các đỉnh active có đóng góp.

Một biến đơn `best[c]=min dist(c,u)` rất tốt khi **chỉ đánh dấu tăng dần** (không xóa). Nhưng với **toggle**, nếu ta tắt chính đỉnh tạo best[c], phải biết đỉnh active kế tiếp để khôi phục min. Đa tập giải quyết bài toán đó.

### Công thức nearest

Với đỉnh hỏi v, xét tất cả Step(v,c):

**`nearest(v)=min_c [dist(v,c)+min D_c]`**,

chỉ xét c có `D_c` không rỗng. Nếu không có đỉnh active nào, trả −1.

Mỗi hạng tử biểu diễn độ dài đường đi từ v qua c tới một đỉnh active u, có thể không là đường ngắn nhất thật. Nhưng bất đẳng thức tam giác bảo đảm:

**`dist(v,u)≤dist(v,c)+dist(c,u)`.**

Do đó mỗi ứng viên qua c **không bao giờ thấp hơn** khoảng cách thật đến u, tức không thể tạo một kết quả “quá tốt” giả. Hơn nữa, với một cặp v,u, tồn tại một centroid tổ tiên chung **nằm trên đường v↔u**, cụ thể centroid thấp nhất trong cây trọng tâm chứa cả v và u trước khi chúng bị tách. Ở centroid ấy có đẳng thức khoảng cách. Vì vậy lấy min qua mọi centroid tổ tiên cho kết quả **chính xác**.

### Nếu v đang active?

Chính v đóng góp khoảng cách 0 vào Step của nó tại centroid v, nên `nearest(v)=0`. Không cần xử lý riêng, miễn quy ước truy vấn cho phép tính v trong tập ứng viên. Nếu đề yêu cầu “đỉnh active **khác** v gần nhất”, cần một cấu trúc/quy tắc riêng, không tự trừ 1 khỏi kết quả.

### Độ phức tạp với TreeMap

Mỗi v có O(log n) Step. Chèn/xóa một tần suất trong `TreeMap` tại mỗi Step tốn O(log n) trường hợp xấu, nên:

- `toggle(v)`: **O(log² n)**.
- `nearest(v)` trong bản mã này: tối đa O(log n) centroid, mỗi `TreeMap.firstKey()` có thể đi O(log n) ⇒ **O(log² n)** theo cận bảo thủ.
- Nếu lưu và bảo trì một **giá trị min riêng** khi update, có thể giảm việc lấy min ở query còn O(log n), với chi phí quản lý cấu trúc khi xóa. Không nên tuyên bố bản TreeMap hiện tại tự động O(log n) cho mọi thao tác.

## 6. Truy vấn đếm active trong bán kính k: cần cộng–trừ nhánh

Ta muốn:

**`countWithin(v,k)=|{u active : dist(v,u)≤k}|`.**

Nếu tại mỗi centroid c chỉ đếm các u có `dist(u,c)≤k−dist(v,c)` rồi cộng qua mọi Step(v,c), ta dễ **đếm nhiều lần** cùng một u. Ví dụ u và v ở cùng một nhánh của c, đường thật u↔v không đi qua c; dù vậy u vẫn có thể xuất hiện trong cấu trúc dữ liệu của centroid c, rồi xuất hiện lại ở centroid sâu hơn.

Để chính xác, ở mỗi centroid c lưu hai loại bộ đếm:

- **`All[c]`:** đa tập các khoảng cách `dist(c,u)` của **mọi u active nằm trong thành phần được xử lý khi chọn c**.
- **`Sub[c][b]`:** đa tập khoảng cách `dist(c,u)` của **những u active thuộc đúng nhánh b của c** trong thành phần ấy.

`All[c]` và `Sub[c][b]` đều lưu khoảng cách từ **c tới u** (không phải khoảng cách từ u tới b). Nhánh `b` lấy theo **hàng xóm trực tiếp của c trong thành phần hiện tại**.

### Công thức inclusion–exclusion

Với mỗi Step của đỉnh hỏi v có `(c,d,b)`, đặt:

**`remaining=k−d`.**

Nếu remaining<0, không đếm gì ở mức c. Nếu remaining≥0, cộng:

**`All[c].countLE(remaining)−(b=−1?0:Sub[c][b].countLE(remaining))`.**

Tổng qua tất cả Step:

**`countWithin(v,k)=Σ_{(c,d,b)∈steps[v]} [All_c(k−d)−Sub_{c,b}(k−d)]`**,

với `Sub_{c,−1}=0` và các bộ đếm tại ngưỡng âm đều bằng 0.

Điều kiện `dist(u,c)≤k−dist(v,c)` tương đương `dist(v,c)+dist(c,u)≤k`. Ta chỉ dùng nó cho những u **không cùng nhánh với v tại c**. Khi ấy c nằm trên đường v↔u, nên tổng là **khoảng cách thật**.

### Vì sao trừ nhánh chứa v làm hết trùng?

Cố định cặp v,u. Đi từ gốc cây trọng tâm xuống:

- Ở mọi centroid c mà v và u còn nằm **cùng một nhánh**, u có trong `All[c]` nhưng cũng trong `Sub[c][branch(v,c)]`, nên đóng góp **bằng 0**.
- Tại **centroid đầu tiên tách v và u** (hoặc c=v/u), u nằm ở nhánh **khác** nhánh của v hoặc chính c. Nó được tính **một lần** nếu khoảng cách thật ≤k.
- Ở các centroid sâu hơn thuộc chuỗi của v, u đã nằm **ngoài thành phần** ấy nên không xuất hiện trong `All[c]` nữa.

Vì vậy mỗi u active đóng góp **đúng một lần hoặc 0 lần** tùy dist(v,u)≤k. Đó là chứng minh chính xác cho phép cộng–trừ nhánh.

### Điều gì xảy ra khi k rất lớn?

Nếu k≥n−1 trong cây không trọng số, mọi đỉnh cách v tối đa n−1 nên kết quả phải bằng **tổng số đỉnh active**. Công thức vẫn đúng; không cần tự xử lý đặc biệt. Nếu k âm, `countWithin(v,k)=0`.

## 7. Hỗ trợ countLE bằng Fenwick và nén khoảng cách

Các khoảng cách trong cây gốc **không thay đổi** khi bật/tắt đỉnh. Vì vậy, tại thời điểm phân rã, ta biết trước:

- Tập tất cả khoảng cách có thể đóng góp vào `All[c]`.
- Tập tất cả khoảng cách có thể đóng góp vào mỗi `Sub[c][b]`.

Ta có thể sắp xếp và **khử trùng** các khoảng cách ấy để tạo mảng tọa độ:

`coords=[d₀<d₁<...<d_{t−1}]`.

Trên mảng này dùng **Fenwick tree (Binary Indexed Tree)** lưu số lần xuất hiện của từng khoảng cách **trong tập active hiện tại**.

### Khi bật/tắt u

Với mỗi Step(u,c,d,b):

- `All[c].add(d,+1)` khi bật, `All[c].add(d,−1)` khi tắt.
- Nếu `b≠−1`, tương tự `Sub[c][b].add(d,±1)`.
- Đồng thời cập nhật TreeMap của centroid c phục vụ `nearest`.

Đối với mỗi Fenwick, tìm vị trí chính xác của d trong coords bằng **binary search**, rồi cập nhật các ô Fenwick theo bước `i += i&−i`.

### Khi hỏi countLE(t)

Tìm **upper bound** trong coords: vị trí đầu tiên có khoảng cách **>t**, tức số tọa độ ≤t. Sau đó lấy tổng tiền tố Fenwick tới chỉ số ấy, đi theo `i -= i&−i`.

Cần phân biệt:

- Tìm kiếm **vị trí đúng bằng d** khi update.
- Tìm kiếm **số phần tử tọa độ ≤t** khi query.

Nếu t không có trong coords, truy vấn vẫn hoàn toàn hợp lệ: upper bound trả số khoảng cách phân biệt không lớn hơn t. Nếu t âm, `countLE(t)=0` vì mọi khoảng cách trong cây không trọng số không âm.

### Vì sao không dùng một Fenwick toàn cây?

Các khoảng cách chỉ có ý nghĩa **tương đối với centroid c**. Một đỉnh u có thể cách các centroid tổ tiên khác nhau với các giá trị khác nhau. Việc cập nhật ở c cần các tọa độ của **thành phần được phân rã tại c**, và ở nhánh b cần một tập con riêng. Một Fenwick chung trên n đỉnh không mô tả được tất cả các khoảng cách tương đối ấy.

## 8. Truy vết bằng cây tám đỉnh

Nhắc lại các cạnh:

`(0,1),(1,2),(1,3),(3,4),(3,5),(5,6),(5,7)`.

Trong cây này, **3 là centroid của cả cây**. Loại 3:

- Nhánh qua 1 có các đỉnh {0,1,2}, kích thước 3.
- Nhánh qua 4 có {4}, kích thước 1.
- Nhánh qua 5 có {5,6,7}, kích thước 3.

Từng nhánh có ≤4 đỉnh, đúng yêu cầu centroid của m=8.

Centroid sâu hơn của {0,1,2} có thể chọn **1**, của {5,6,7} chọn **5**; nhánh {4} chọn **4**. Các đỉnh 0,2,6,7 là centroid ở các thành phần một đỉnh.

### Hai đỉnh active ban đầu: 2 và 6

Tại centroid 3:

- `dist(3,2)=2`.
- `dist(3,6)=2`.
- Vì cả hai active, đa tập `D_3={2,2}`, **giữ hai lần giá trị 2**, không gộp thành một phần tử mất tần suất.

Hỏi `nearest(4)`:

- `dist(4,3)=1`.
- `min D_3=2`.
- Ứng viên qua 3 có độ dài 1+2=**3**, đúng bằng dist(4,2)=dist(4,6)=3.
- Không có đỉnh active gần hơn ⇒ kết quả **3**.

Hỏi `countWithin(4,3)`:

- Step(4,3) có `d=1`, `branch=4`.
- Remaining=3−1=2.
- `All[3].countLE(2)=2` vì 2 và 6 đều cách 3 đúng 2.
- `Sub[3][4].countLE(2)=0` vì nhánh qua 4 chưa có đỉnh active.
- Đóng góp mức 3 là **2**; các mức sâu hơn không thêm đỉnh 2/6 ⇒ kết quả **2**.

Hỏi `countWithin(4,2)`:

- Remaining tại c=3 bằng 1.
- Không đỉnh active nào trong {2,6} có dist đến c≤1 ⇒ đóng góp 0.
- Kết quả **0**.

### Bật thêm đỉnh 5

Khi active={2,5,6}, `dist(4,5)=2`. Vì vậy:

- `nearest(4)=2`.
- `countWithin(4,2)=1` (chỉ 5).
- `countWithin(4,3)=3` (2,5,6).

Khi tắt 6, khoảng cách của 6 phải được xóa khỏi **mọi centroid tổ tiên của 6**, không chỉ centroid sâu nhất. Sau đó `nearest(7)=1` do còn đỉnh active 5.

## 9. Công thức tính đúng của truy vấn nearest

Gọi A là tập đỉnh active, v là đỉnh hỏi. Với mỗi centroid tổ tiên c của v:

`Q_c(v)=dist(v,c)+min_{u∈A∩component(c)}dist(c,u)`,

nếu tập ứng viên không rỗng. Thuật toán trả min của các Q_c.

**Cận không quá lạc quan sai:** với mọi c và u trong tập ấy, bất đẳng thức tam giác cho:

`dist(v,u)≤dist(v,c)+dist(c,u)`.

Do đó một giá trị Q_c không thể **nhỏ hơn khoảng cách thật nhỏ nhất** tới một đỉnh active. Việc lấy min qua các centroid không thể cho câu trả lời thấp giả.

**Có ứng viên đạt đúng:** chọn u* là đỉnh active gần v nhất. Xét centroid tổ tiên chung thấp nhất của v và u* trong cây trọng tâm, gọi là c*. Trước khi tách ở c*, cả hai còn nằm trong cùng thành phần; sau khi bỏ c* chúng nằm ở hai nhánh khác nhau hoặc một đỉnh chính là c*. Vì vậy c* nằm trên **đường đi đơn** từ v tới u*:

`dist(v,u*)=dist(v,c*)+dist(c*,u*)`.

Đỉnh u* có đóng góp vào `D_{c*}` nên `min D_{c*}≤dist(c*,u*)`. Do đó:

`Q_{c*}(v)≤dist(v,c*)+dist(c*,u*)=dist(v,u*)`.

Kết hợp hai chiều, min qua các Q_c **bằng chính xác nearest(v)**.

**Chú ý:** Q_c có thể dùng một u không nằm phía bên kia c, khiến đường qua c dài hơn đường thật. Điều ấy không gây sai cho **min** nhờ bất đẳng thức tam giác và sự tồn tại c* đạt đúng. Với **count**, không thể dùng lập luận này để cộng thẳng Q_c; phải dùng nhánh loại trừ.

## 10. Công thức tính đúng của countWithin

Ta chứng minh mỗi đỉnh u active có đúng một cơ hội được tính.

Xét v,u bất kỳ. Trên cây trọng tâm, lấy c* là **centroid tổ tiên chung thấp nhất**. Nếu c nằm trên chuỗi tổ tiên của v **phía trên c***, v và u thuộc **cùng một nhánh** trong thành phần của c: contribution của u bị cộng ở `All[c]` nhưng **bị trừ ở `Sub[c][branch(v,c)]`**.

Ở c*, v và u thuộc **hai nhánh khác nhau**, hoặc một trong chúng chính là c*, nên u nằm trong All nhưng **không** thuộc Sub của nhánh chứa v. Vì c* nằm trên đường gốc nối v và u:

`dist(v,u)=dist(v,c*)+dist(c*,u)`.

Do đó u được tính tại c* **khi và chỉ khi** `dist(v,u)≤k`.

Với các centroid tổ tiên của v **thấp hơn c***, thành phần đang xét không còn chứa u, nên nó không xuất hiện trong All. Vậy u đóng góp:

- **1 lần** nếu active và nằm trong bán kính;
- **0 lần** nếu active nhưng ngoài bán kính;
- **0 lần** nếu inactive.

Cộng qua mọi u thu được đúng `countWithin(v,k)`, không trùng và không thiếu.

### Vì sao sub phải lưu dist từ centroid c?

Ta kiểm tra `dist(v,c)+dist(c,u)≤k`. Vì vậy cả All và Sub cần đếm theo **`dist(c,u)`**, cùng một hệ quy chiếu. Nếu Sub lưu dist từ **đỉnh gốc nhánh b** tới u, phép trừ sử dụng ngưỡng k−dist(v,c) sẽ không còn tương ứng với những ứng viên All cần loại.

## 11. Phân tích thời gian và bộ nhớ

Đặt n là số đỉnh của cây.

| Công việc | Thời gian |
|---|---:|
| Kiểm tra đầu vào và xây adjacency list | O(n) |
| Chọn các centroid và duyệt các thành phần qua các mức phân rã | **O(n log n)** |
| Thu thập các Step(v,c) và khoảng cách từ centroid | **O(n log n)** |
| Sắp và khử trùng tọa độ cho các Fenwick của All và Sub | **O(n log² n)** cận an toàn |
| `toggle(v)` cập nhật Fenwick và TreeMap | **O(log² n)** |
| `nearest(v)` trên các TreeMap | **O(log² n)** cận bảo thủ |
| `countWithin(v,k)` với Fenwick và binary search | **O(log² n)** |

**Bộ nhớ:** **`O(n log n)`** cho tất cả Step, mảng tọa độ và cây Fenwick của All/Sub, cộng O(n) adjacency list, mảng DSU kiểm tra, trạng thái active và stack tạm. Cây trọng tâm có n đỉnh, chiều cao O(log n); các thao tác DFS theo thành phần dùng stack tường minh O(n).

### Vì sao lại O(n log² n) khi build?

Mỗi đỉnh thuộc tối đa O(log n) thành phần trên chuỗi phân rã, nên có O(n log n) lần ghi khoảng cách. Nhưng mảng khoảng cách của mỗi centroid/nhánh còn được **sắp xếp** để tạo Fenwick. Một centroid với m đỉnh có chi phí sorting O(m log m); cộng trên O(log n) mức phân rã cho cận an toàn **O(n log² n)**. Các kỹ thuật nén/tổ chức khác có thể cải thiện cận build, nhưng không được tự gán độ phức tạp ấy cho bản Java đang dùng `Arrays.sort` ở từng mảng.

### Chi phí bản code hỗ trợ cả hai kiểu truy vấn

Nếu chỉ cần **nearest** và không có **countWithin**, có thể bỏ tất cả Fenwick All/Sub và chỉ giữ TreeMap tại mỗi centroid. Nếu chỉ đánh dấu thêm mà **không bao giờ tắt**, có thể dùng một giá trị min[c] cho mỗi centroid và đơn giản hóa cập nhật/nhớ dữ liệu. Nếu chỉ đếm trong bán kính trên cây tĩnh không cập nhật, có thể chọn một cách tiền xử lý khác rẻ hơn.

**Không phải truy vấn “khoảng cách trên cây” nào cũng nên dùng centroid decomposition.** Nếu chỉ hỏi `dist(u,v)` cho từng cặp u,v trên cây cố định, **LCA** sau tiền xử lý có thể trả nhanh hơn và đơn giản hơn. Centroid decomposition đặc biệt phù hợp khi các **đỉnh có trạng thái động** và truy vấn liên quan đến khoảng cách tới một **tập đỉnh**.

## 12. Java 17+ hoàn chỉnh: toggle, nearest, countWithin

Chương trình nhận **cây không trọng số**. Mọi cạnh có độ dài 1; khoảng cách không âm và lớn nhất n−1, nên lưu trong `int`. Khi cộng hai khoảng cách trung gian cho ứng viên nearest, mã dùng `long` để tránh tràn trung gian trước khi lấy min. Vì có ít nhất một đỉnh active, đáp án gần nhất cuối luôn là khoảng cách thật trên cây, nên nằm trong khoảng `0..n−1` và có thể trả `int`.

Thiết kế:

- **`DSU`** để kiểm tra danh sách n−1 cạnh không chu trình. Trong đồ thị vô hướng có n đỉnh, n−1 cạnh và không chu trình ⇒ cây liên thông.
- **`findCentroid`** dùng DFS iterative, `parentScan` và `subtreeSize`; không dùng recursion theo đường dài trong cây gốc.
- **`decompose`** chọn centroid, gắn Step(c,d,b) cho các đỉnh thuộc thành phần, xây tọa độ của All và từng nhánh. Đệ quy chỉ theo các thành phần có kích thước ≤1/2.
- **`Fenwick`** nén khoảng cách bằng sorting, hỗ trợ `add(distance,±1)` và `countLE(radius)`.
- **`TreeMap<Integer,Integer>`** là multiset khoảng cách active tại mỗi centroid, hỗ trợ bật/tắt.
- Mảng `steps[v]` giữ các centroid từ trên xuống của v; cả update lẫn query chỉ duyệt mảng ấy.

**Hợp đồng của chương trình:** n≥1; danh sách cạnh có đúng n−1 phần tử, mỗi phần tử là hai endpoint hợp lệ khác nhau; đồ thị phải không có chu trình; `toggle`, `nearest` và `countWithin` yêu cầu v hợp lệ. Khi chưa có đỉnh active, nearest trả −1, count trả 0. Khi radius âm, count trả 0. Các phương thức làm việc với chỉ số **0-based** và việc đếm **bao gồm chính v** nếu nó active.

Lưu thành **`CentroidDistanceDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class CentroidDistanceDemo {
    private static final class DSU {
        private final int[] parent;
        private final int[] size;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        private int find(int v) {
            while (parent[v] != v) {
                parent[v] = parent[parent[v]];
                v = parent[v];
            }
            return v;
        }

        boolean union(int a, int b) {
            a = find(a);
            b = find(b);
            if (a == b) {
                return false;
            }
            if (size[a] < size[b]) {
                int t = a;
                a = b;
                b = t;
            }
            parent[b] = a;
            size[a] += size[b];
            return true;
        }
    }

    private static final class Step {
        final int centroid;
        final int distance;
        final int branch; // -1 iff the vertex is this centroid.

        Step(int centroid, int distance, int branch) {
            this.centroid = centroid;
            this.distance = distance;
            this.branch = branch;
        }
    }

    private static final class Walk {
        final int vertex;
        final int parent;
        final int distance;

        Walk(int vertex, int parent, int distance) {
            this.vertex = vertex;
            this.parent = parent;
            this.distance = distance;
        }
    }

    private static final class Fenwick {
        private final int[] coords;
        private final int[] bit;

        Fenwick(List<Integer> distances) {
            int[] values = new int[distances.size()];
            for (int i = 0; i < values.length; i++) {
                values[i] = distances.get(i);
            }
            Arrays.sort(values);
            int count = 0;
            for (int x : values) {
                if (count == 0 || values[count - 1] != x) {
                    values[count++] = x;
                }
            }
            coords = Arrays.copyOf(values, count);
            bit = new int[count + 1];
        }

        void add(int distance, int delta) {
            int pos = Arrays.binarySearch(coords, distance);
            if (pos < 0) {
                throw new IllegalStateException(
                        "Distance not preprocessed");
            }
            for (int i = pos + 1; i < bit.length; i += i & -i) {
                bit[i] += delta;
            }
        }

        int countLE(int radius) {
            int lo = 0;
            int hi = coords.length;
            // Upper bound: number of distinct coords <= radius.
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (coords[mid] <= radius) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            int sum = 0;
            for (int i = lo; i > 0; i -= i & -i) {
                sum += bit[i];
            }
            return sum;
        }
    }

    private static final class Solver {
        private final int n;
        private final List<Integer>[] graph;
        private final boolean[] removed;
        private final int[] parentScan;
        private final int[] subtreeSize;
        private final int[] centroidParent;
        private final List<Step>[] steps;
        private final Fenwick[] allCount;
        private final Map<Integer, Fenwick>[] branchCount;
        private final TreeMap<Integer, Integer>[] activeDistances;
        private final boolean[] active;
        private int activeCount;

        @SuppressWarnings("unchecked")
        Solver(int n, int[][] edges) {
            if (n <= 0 || edges == null || edges.length != n - 1) {
                throw new IllegalArgumentException("Invalid tree size");
            }
            this.n = n;
            graph = (List<Integer>[]) new List[n];
            steps = (List<Step>[]) new List[n];
            branchCount = (Map<Integer, Fenwick>[]) new Map[n];
            activeDistances =
                    (TreeMap<Integer, Integer>[]) new TreeMap[n];
            removed = new boolean[n];
            parentScan = new int[n];
            subtreeSize = new int[n];
            centroidParent = new int[n];
            allCount = new Fenwick[n];
            active = new boolean[n];
            activeCount = 0;

            DSU check = new DSU(n);
            for (int v = 0; v < n; v++) {
                graph[v] = new ArrayList<>();
                steps[v] = new ArrayList<>();
            }
            for (int[] edge : edges) {
                if (edge == null || edge.length != 2) {
                    throw new IllegalArgumentException("Invalid edge");
                }
                int u = edge[0], v = edge[1];
                if (u < 0 || u >= n || v < 0 || v >= n
                        || !check.union(u, v)) {
                    throw new IllegalArgumentException(
                            "Invalid tree edge or cycle");
                }
                graph[u].add(v);
                graph[v].add(u);
            }

            // n-1 valid non-cycle edges force connectedness.
            decompose(0, -1);
        }

        private int findCentroid(int start) {
            List<Integer> order = new ArrayList<>();
            ArrayDeque<Integer> stack = new ArrayDeque<>();
            parentScan[start] = -1;
            stack.push(start);

            while (!stack.isEmpty()) {
                int v = stack.pop();
                order.add(v);
                for (int u : graph[v]) {
                    if (!removed[u] && u != parentScan[v]) {
                        parentScan[u] = v;
                        stack.push(u);
                    }
                }
            }

            for (int v : order) {
                subtreeSize[v] = 1;
            }
            for (int i = order.size() - 1; i >= 0; i--) {
                int v = order.get(i);
                if (parentScan[v] != -1) {
                    subtreeSize[parentScan[v]] += subtreeSize[v];
                }
            }

            int total = order.size();
            for (int v : order) {
                int largest = total - subtreeSize[v];
                for (int u : graph[v]) {
                    if (!removed[u] && parentScan[u] == v) {
                        largest = Math.max(largest, subtreeSize[u]);
                    }
                }
                if (largest <= total / 2) {
                    return v;
                }
            }
            throw new IllegalStateException("Centroid not found");
        }

        private void decompose(int start, int parent) {
            int centroid = findCentroid(start);
            removed[centroid] = true;
            centroidParent[centroid] = parent;

            List<Integer> allDistances = new ArrayList<>();
            Map<Integer, List<Integer>> perBranch = new HashMap<>();
            allDistances.add(0);
            steps[centroid].add(new Step(centroid, 0, -1));

            // Every remaining neighbor is one distinct branch.
            for (int neighbor : graph[centroid]) {
                if (removed[neighbor]) {
                    continue;
                }
                List<Integer> branchDistances = new ArrayList<>();
                perBranch.put(neighbor, branchDistances);
                ArrayDeque<Walk> stack = new ArrayDeque<>();
                stack.push(new Walk(neighbor, centroid, 1));

                while (!stack.isEmpty()) {
                    Walk w = stack.pop();
                    steps[w.vertex].add(new Step(
                            centroid, w.distance, neighbor));
                    allDistances.add(w.distance);
                    branchDistances.add(w.distance);
                    for (int u : graph[w.vertex]) {
                        if (u != w.parent && !removed[u]) {
                            stack.push(new Walk(
                                    u, w.vertex, w.distance + 1));
                        }
                    }
                }
            }

            allCount[centroid] = new Fenwick(allDistances);
            branchCount[centroid] = new HashMap<>();
            for (Map.Entry<Integer, List<Integer>> entry
                    : perBranch.entrySet()) {
                branchCount[centroid].put(
                        entry.getKey(), new Fenwick(entry.getValue()));
            }
            activeDistances[centroid] = new TreeMap<>();

            // Recursion only on components of at most half size.
            for (int neighbor : graph[centroid]) {
                if (!removed[neighbor]) {
                    decompose(neighbor, centroid);
                }
            }
        }

        private void checkVertex(int v) {
            if (v < 0 || v >= n) {
                throw new IllegalArgumentException(
                        "Vertex out of range");
            }
        }

        void toggle(int v) {
            checkVertex(v);
            boolean turnOn = !active[v];
            int delta = turnOn ? 1 : -1;

            for (Step step : steps[v]) {
                int c = step.centroid;
                int d = step.distance;
                allCount[c].add(d, delta);
                if (step.branch != -1) {
                    branchCount[c].get(step.branch).add(d, delta);
                }

                TreeMap<Integer, Integer> bag = activeDistances[c];
                if (turnOn) {
                    bag.merge(d, 1, Integer::sum);
                } else {
                    Integer frequency = bag.get(d);
                    if (frequency == null) {
                        throw new IllegalStateException(
                                "Broken active-distance multiset");
                    }
                    if (frequency == 1) {
                        bag.remove(d);
                    } else {
                        bag.put(d, frequency - 1);
                    }
                }
            }

            active[v] = turnOn;
            activeCount += delta;
        }

        int nearest(int v) {
            checkVertex(v);
            if (activeCount == 0) {
                return -1;
            }
            long best = Long.MAX_VALUE;
            for (Step step : steps[v]) {
                TreeMap<Integer, Integer> bag =
                        activeDistances[step.centroid];
                if (!bag.isEmpty()) {
                    long candidate = (long) step.distance
                            + bag.firstKey();
                    best = Math.min(best, candidate);
                }
            }
            if (best == Long.MAX_VALUE) {
                throw new IllegalStateException("Missing active vertex");
            }
            // The true tree distance is <= n-1 and fits an int.
            return (int) best;
        }

        int countWithin(int v, int radius) {
            checkVertex(v);
            if (radius < 0) {
                return 0;
            }
            int answer = 0;
            for (Step step : steps[v]) {
                int remaining = radius - step.distance;
                if (remaining < 0) {
                    continue;
                }
                int c = step.centroid;
                answer += allCount[c].countLE(remaining);
                if (step.branch != -1) {
                    answer -= branchCount[c].get(step.branch)
                            .countLE(remaining);
                }
            }
            return answer;
        }
    }

    public static void main(String[] args) {
        Solver tree = new Solver(8, new int[][] {
            {0, 1}, {1, 2}, {1, 3}, {3, 4},
            {3, 5}, {5, 6}, {5, 7}
        });

        System.out.println("Initially nearest(4): "
                + tree.nearest(4));
        System.out.println("Initially count(4,3): "
                + tree.countWithin(4, 3));

        tree.toggle(2);
        tree.toggle(6);
        System.out.println("After activate 2,6 nearest(4): "
                + tree.nearest(4));
        System.out.println("After activate 2,6 count(4,2): "
                + tree.countWithin(4, 2));
        System.out.println("After activate 2,6 count(4,3): "
                + tree.countWithin(4, 3));
        System.out.println("After activate 2,6 nearest(7): "
                + tree.nearest(7));
        System.out.println("After activate 2,6 count(7,2): "
                + tree.countWithin(7, 2));

        tree.toggle(5);
        System.out.println("After activate 5 nearest(4): "
                + tree.nearest(4));
        System.out.println("After activate 5 count(4,2): "
                + tree.countWithin(4, 2));
        System.out.println("After activate 5 count(4,3): "
                + tree.countWithin(4, 3));

        tree.toggle(6);
        System.out.println("After deactivate 6 nearest(7): "
                + tree.nearest(7));
        System.out.println("After deactivate 6 count(7,2): "
                + tree.countWithin(7, 2));

        tree.toggle(2);
        tree.toggle(5);
        System.out.println("After clear nearest(4): "
                + tree.nearest(4));
        System.out.println("After clear count(4,4): "
                + tree.countWithin(4, 4));

        tree.toggle(1);
        System.out.println("Active itself nearest(1): "
                + tree.nearest(1));
        System.out.println("Active itself count(1,0): "
                + tree.countWithin(1, 0));
    }
}
~~~

Biên dịch và chạy với **JDK 17 hoặc mới hơn**:

~~~bash
javac CentroidDistanceDemo.java
java CentroidDistanceDemo
~~~

**Đầu ra chuẩn chính xác:**

~~~text
Initially nearest(4): -1
Initially count(4,3): 0
After activate 2,6 nearest(4): 3
After activate 2,6 count(4,2): 0
After activate 2,6 count(4,3): 2
After activate 2,6 nearest(7): 2
After activate 2,6 count(7,2): 1
After activate 5 nearest(4): 2
After activate 5 count(4,2): 1
After activate 5 count(4,3): 3
After deactivate 6 nearest(7): 1
After deactivate 6 count(7,2): 1
After clear nearest(4): -1
After clear count(4,4): 0
Active itself nearest(1): 0
Active itself count(1,0): 1
~~~

### Vì sao tìm centroid không tràn stack theo độ sâu cây gốc?

Phương thức `findCentroid` dùng `ArrayDeque` để duyệt thành phần, ghi `parentScan` và danh sách `order`. Sau khi biết thứ tự, nó đi ngược `order` để cộng `subtreeSize` cho cha. Không có đệ quy DFS theo từng cạnh cây.

Lúc `decompose` xây khoảng cách, nó cũng dùng stack chứa `Walk(vertex,parent,distance)`. Chỉ **lời gọi decompose trên một thành phần sau khi bỏ centroid** mới là đệ quy; mỗi nhánh có kích thước ≤m/2 nên độ sâu O(log n).

### Tại sao parentScan được tái sử dụng?

Mỗi lần tìm centroid chỉ duyệt một **thành phần liên thông đang chưa bị loại**, là một cây. Tất cả đỉnh thuộc thành phần ấy được gán lại parentScan trong lần duyệt hiện tại; các đỉnh đã removed bị bỏ qua. Vì không có chu trình, kiểm tra neighbor≠parent là đủ. Sau khi tìm centroid, dữ liệu parentScan/subtreeSize không còn cần cho mức ấy; lời gọi decompose con có thể dùng lại mảng mà không phá dữ liệu còn dùng ở mức cha.

### Vì sao cập nhật tại mọi Step?

Mỗi active u đóng góp vào tất cả centroid tổ tiên c mà u nằm trong thành phần tại thời điểm chọn c. Nếu chỉ cập nhật centroid thấp nhất của u, câu hỏi từ một đỉnh v ở **nhánh khác** không thể thấy u qua centroid phân tách chung.

### Vì sao không tạo Fenwick cho từng đỉnh/nhóm bất kỳ?

`All[c]` có các tọa độ của những đỉnh thuộc **thành phần ban đầu của centroid c**, còn `Sub[c][b]` có tọa độ của **nhánh b** trong chính thành phần ấy. Những tập đó là dữ liệu **tĩnh** theo cây gốc và không phụ thuộc trạng thái active; chỉ giá trị đếm trong Fenwick thay đổi.

### Vì sao có TreeMap lẫn Fenwick?

`TreeMap` cho phép lấy khoảng cách **nhỏ nhất** và xóa một lần xuất hiện khi toggle. `Fenwick` cho phép đếm số khoảng cách **≤ngưỡng bất kỳ**. Một min không trả số lượng, còn Fenwick có thể tìm min bằng kỹ thuật khác nhưng code này giữ hai cấu trúc để làm rõ hai dạng truy vấn và chứng minh độc lập.

## 13. Những trường hợp biên cần xử lý

| Trường hợp | Kết quả/điểm cần nhớ |
|---|---|
| n=1, không cạnh | Có một centroid là đỉnh 0 |
| Chưa active đỉnh nào | nearest(v)=−1, countWithin(v,k)=0 |
| Active chính v | nearest(v)=0, countWithin(v,0)≥1 |
| Toggle(v) hai lần | Trạng thái quay lại ban đầu |
| Hai đỉnh cùng dist tới centroid | TreeMap cần tần suất, không xóa cả khóa |
| k<0 | countWithin(v,k)=0 |
| k=0 | Chỉ tính chính v nếu active |
| k≥n−1 | countWithin(v,k)=số active toàn cây |
| Cây đường thẳng | Centroid depth vẫn O(log n) |
| Cây hình sao | Centroid gốc thường là trung tâm hình sao |
| Cây có hai centroid hợp lệ | Chọn một trong hai, kết quả truy vấn vẫn đúng |
| Đỉnh không hợp lệ | API ném IllegalArgumentException |
| Danh sách cạnh tạo chu trình hoặc trùng cạnh gây chu trình | Input bị từ chối |
| Danh sách không đủ n−1 cạnh | Input bị từ chối |
| Cây rất sâu | DFS iterative tránh recursion theo cây gốc |
| Query bán kính lớn | Kết quả không vượt số đỉnh active |
| Nhiều thao tác bật/tắt cùng một đỉnh | Không bị âm tần suất nếu logic toggle đúng |

### Đầu vào có trọng số cạnh

Phiên bản trình bày dùng cạnh đơn vị. Với cây **có trọng số không âm**, ý tưởng centroid decomposition vẫn dùng được, nhưng phải:

- Lưu **khoảng cách trọng số từ c tới u**, thường dùng `long` hoặc số chính xác hơn.
- Kiểm soát tràn ở phép cộng trọng số/ứng viên.
- Nén tọa độ kiểu long trong Fenwick; xử lý bán kính k theo cùng kiểu.
- Giữ dữ liệu nhánh theo centroid như trước.

Nếu có **cạnh trọng số âm**, khoảng cách trên cây theo tổng cạnh không còn là **metric không âm**; bất đẳng thức tam giác dùng trong chứng minh `nearest` qua centroid không còn được bảo đảm khi c không nằm trên đường u↔v. Vì vậy **không được áp dụng nguyên công thức min không lọc nhánh** cho trọng số âm. Có thể cần thuật toán/biến đổi khác phù hợp với bài toán.

## 14. Các biến thể cần phân biệt

### 14.1. Chỉ thêm đỉnh đánh dấu, không xóa

Nếu mỗi đỉnh chỉ đổi inactive→active một lần, tại mỗi centroid c có thể giữ:

**`best[c]=min_{u active}dist(c,u)`**.

Khi mark(u), cập nhật best[c] qua mọi centroid tổ tiên của u. Khi query(v), trả min `dist(v,c)+best[c]`. Mỗi thao tác chỉ qua O(log n) centroid, không cần TreeMap hoặc Fenwick. Nhưng mô hình này **không hỗ trợ unmark** đúng, vì giá trị min cũ có thể do một đỉnh đã tắt tạo ra.

### 14.2. Tổng khoảng cách tới mọi đỉnh active

Muốn tính **`sum_{u active}dist(v,u)`**, tại mỗi centroid lưu **số lượng** và **tổng khoảng cách từ centroid tới các đỉnh active**, kèm các đại lượng tương ứng theo nhánh. Khi query(v), cộng **`sumDist[c]+count[c]·dist(v,c)`**, rồi trừ bản sao của nhánh chứa v. Đây là phiên bản cộng–trừ tương tự countWithin, nhưng giá trị cần lưu và phép tính khác. Với số active lớn, tổng có thể cần `long` hoặc kiểu rộng hơn.

### 14.3. Đếm cặp active có khoảng cách không quá k

Nếu đề hỏi số **cặp đỉnh active** có khoảng cách trong ngưỡng, thay vì `countWithin` từ một v, có thể áp dụng phân rã trọng tâm để đếm các cặp đi qua centroid, trừ cặp nằm cùng nhánh, hoặc kết hợp cấu trúc cập nhật nếu có thay đổi trạng thái. Nhưng một bài đếm **tất cả cặp sau mỗi toggle** có yêu cầu khác với query từ **một đỉnh**; cần phân tích cách duy trì kết quả toàn cục.

### 14.4. Hỏi khoảng cách giữa hai đỉnh u,v

Nếu cây cố định và truy vấn chỉ hỏi `dist(u,v)`, cách thường dùng là **LCA (lowest common ancestor)**. Sau khi chọn gốc, với độ sâu `depth`:

**`dist(u,v)=depth[u]+depth[v]−2·depth[LCA(u,v)]`**

cho cây không trọng số. Tiền xử lý binary lifting O(n log n), mỗi query O(log n); có những phương pháp LCA khác nhanh hơn tùy dữ liệu. Centroid decomposition không phải công cụ bắt buộc cho truy vấn đơn cặp này.

### 14.5. Cạnh hoặc cấu trúc cây thay đổi

Code ở đây cho phép **trạng thái active đổi**, nhưng **các cạnh cây không đổi**. Nếu thêm/xóa cạnh, đổi trọng số, hoặc thay liên thông, mảng centroid và khoảng cách tiền xử lý có thể không còn đúng. Đó là bài toán **dynamic tree** khác, có thể cần link-cut tree, Euler-tour tree hoặc xây lại tùy tính chất cập nhật.

### 14.6. Truy vấn khoảng cách chính xác bằng k

Với `countWithin(v,k)` trả số active có dist≤k, có thể tính:

**`countExactly(v,k)=countWithin(v,k)−countWithin(v,k−1)`**,

khi k≥0. Với k=0, `countWithin(v,−1)=0`. Nếu k là `Integer.MIN_VALUE` trong Java thì k−1 tràn; nên xử lý k<0 trước, hoặc dùng kiểu rộng hơn khi biến thể cho phép k ngoài phạm vi.

## 15. Những lỗi phổ biến

1. **Nhầm centroid với trung tâm theo eccentricity:** tiêu chí centroid dùng **kích thước các phần sau khi bỏ đỉnh**, không phải tối đa khoảng cách.
2. **Không tính phần phía cha khi tìm centroid:** một đỉnh có cây con nhỏ vẫn có phần còn lại rất lớn.
3. **Không loại centroid trước khi duyệt nhánh:** có thể quay lại qua centroid và lặp vô hạn.
4. **Chỉ lưu khoảng cách trên cây trọng tâm:** truy vấn cần `dist_G(v,c)` trong **cây gốc**.
5. **Không lưu Step cho centroid chính nó:** mất trường hợp dist=0, countWithin(v,0).
6. **Không nhận diện nhánh chứa v tại c:** không thể trừ phần bị đếm trùng.
7. **Sử dụng branch của cây trọng tâm thay cho nhánh gốc tại c một cách không chứng minh:** cần định nghĩa nhánh theo thành phần khi bỏ c.
8. **Đếm bằng tổng All[c] mà không trừ Sub[c][b]:** một u có thể bị đếm nhiều lần.
9. **Sub lưu dist(u,b) thay vì dist(u,c):** ngưỡng so sánh k−dist(v,c) không còn đúng.
10. **Dùng Set thay vì multiset cho nearest:** xóa một đỉnh làm mất khoảng cách trùng của đỉnh khác còn active.
11. **Chỉ cập nhật centroid gần nhất của u:** không cập nhật tại các centroid tổ tiên chung với v.
12. **Quên hoàn tác Fenwick của Sub khi unmark:** countWithin sai sau toggle.
13. **Không kiểm tra active[v] trước khi chọn dấu ±1:** có thể tạo tần suất âm.
14. **Thấy một ứng viên nearest qua c lớn hơn đường thật rồi sửa công thức tùy tiện:** ứng viên có thể lớn hơn, nhưng lấy min qua các centroid bảo đảm có một ứng viên chính xác.
15. **Dùng sum qua centroid thay cho min trong nearest:** hoàn toàn khác bài toán.
16. **Sai lower_bound/upper_bound khi đếm ≤k:** nếu dùng lower_bound sẽ bỏ sót đúng các đỉnh cách bằng k.
17. **Không nén tọa độ riêng cho centroid/nhánh:** khoảng cách tĩnh ở mỗi hệ quy chiếu khác nhau.
18. **Tràn khoảng cách/trung gian ở biến thể cây có trọng số:** chọn kiểu số phù hợp.
19. **Cho phép cạnh âm mà vẫn dùng chứng minh bất đẳng thức tam giác:** công thức nearest có thể sai.
20. **Coi chuỗi centroid ancestor là đường trong cây gốc:** đường centroid tree là cấu trúc phân cấp khác.
21. **DFS đệ quy sâu theo cây gốc:** cây đường thẳng có thể gây tràn stack.
22. **Dùng thuật toán cho cây với đồ thị có chu trình:** parent check không đủ tránh lặp, centroid invariant không còn áp dụng trực tiếp.
23. **Quên n=1 hoặc k<0:** lỗi chỉ số và trả kết quả âm giả.
24. **Không tính chi phí sorting Fenwick khi phân tích build:** bản này có cận build O(n log² n), không chỉ O(n log n).
25. **Tắt một đỉnh rồi vẫn để tần suất 1 trong TreeMap:** nearest có thể trả khoảng cách tới đỉnh không còn active.

## 16. Kiểm thử độc lập bằng BFS

Một kiểm thử chất lượng tốt cần đối chiếu với **thuật toán khác** trên cây nhỏ, thay vì tự so hai phiên bản centroid decomposition cùng logic.

Với cây không trọng số và n nhỏ, tiền tính ma trận khoảng cách bằng **BFS từ từng đỉnh**:

1. Với mỗi s, chạy BFS trên adjacency list để tính `dist[s][v]`.
2. Duy trì mảng boolean `active[v]` đơn giản theo các lần toggle.
3. Sau mỗi thao tác hỏi:
   - `expectedNearest=min(dist[v][u])` qua những u active, hoặc −1 nếu rỗng.
   - `expectedCount=Σ_{u active}[dist[v][u]≤k]`.
4. So các kết quả với `nearest` và `countWithin` của centroid decomposition.

Chi phí của oracle là O(n²) để tiền tính tất cả BFS trên cây, và O(n) mỗi query, nhưng với n≤30 trong test thì rất nhẹ và độc lập với công thức cộng–trừ theo centroid.

### Gợi ý kiểm thử ngẫu nhiên

Để sinh cây ngẫu nhiên **chắc chắn liên thông và không chu trình**, cho `v=1..n−1` chọn cha `p_v∈[0,v−1]` và thêm cạnh `(v,p_v)`. Tạo nhiều dạng cây: hình sao, đường thẳng, cây nhị phân, cây ngẫu nhiên mất cân đối.

Sau đó xen kẽ:

- Toggle một đỉnh ngẫu nhiên, kể cả toggle **hai lần liên tiếp**.
- Hỏi nearest từ một đỉnh ngẫu nhiên, kể cả khi chưa active hoặc khi chính v active.
- Hỏi countWithin với radius âm, bằng 0, sát đường kính và lớn hơn n.
- Bật nhiều đỉnh có **cùng khoảng cách đến một centroid**, rồi tắt từng đỉnh để kiểm tra tần suất.
- Kiểm tra tính chất `countWithin(v,k)` **không giảm** theo k.
- Kiểm tra `0≤countWithin(v,k)≤activeCount`.
- Khi activeCount>0, `0≤nearest(v)≤n−1`.
- Khi k≥n−1, `countWithin(v,k)=activeCount`.
- Khi k=0, `countWithin(v,0)` bằng 1 nếu v active, ngược lại 0.

### Ca biên riêng cho input và tính đúng

| Input | Kết quả |
|---|---|
| n=1, edges rỗng | Cây hợp lệ, một centroid |
| n=0 | Bị từ chối theo hợp đồng |
| Thiếu cạnh, edges.length≠n−1 | Bị từ chối |
| Cạnh u=u | Bị từ chối như chu trình |
| Cạnh song song tạo chu trình trong tập n−1 cạnh | Bị từ chối |
| Endpoint âm hoặc ≥n | Bị từ chối |
| Toggle đỉnh ngoài phạm vi | IllegalArgumentException |
| Query v ngoài phạm vi | IllegalArgumentException |
| Không active | nearest=-1 và count=0 |
| Toggle hai lần | Quay lại trạng thái cũ, không còn tần suất |
| Nhiều active cùng khoảng cách | TreeMap giữ đúng bội số |
| n lớn, đường thẳng sâu | Không dùng DFS recursion theo độ sâu gốc |

### Kiểm tra chiều sâu centroid tree

Có thể đếm `steps[v].size()` cho từng v. Với n≥1, số mức là O(log n). Nếu kết quả lớn gần n trên cây đường thẳng, nhiều khả năng ta đang chọn đỉnh chia sai hoặc không loại centroid đúng lúc.

Nên kiểm tra điều kiện **max component size ≤ m/2** ở mỗi bước phân rã trên cây nhỏ. Một thuật toán có thể vẫn trả kết quả truy vấn đúng nếu cấu trúc phân rã chưa cân bằng, nhưng sẽ mất bảo đảm về **độ phức tạp logarit**.

## 17. Checklist khi giải bài khoảng cách bằng centroid decomposition

- Cấu trúc đầu vào có thực sự là **cây tĩnh**, không phải đồ thị tổng quát?
- Khoảng cách là số cạnh hay tổng trọng số? Có cạnh âm không?
- Centroid được chọn theo kích thước thành phần **sau khi loại**, có kiểm tra cả phía cha?
- Sau khi chọn centroid, có đánh dấu removed và chỉ duyệt các thành phần chưa bị loại?
- Mỗi đỉnh có lưu đầy đủ **tổ tiên centroid, dist gốc, branch ở centroid**?
- Độ sâu cây trọng tâm có O(log n), tổng Step O(n log n)?
- Với nearest, có lưu đủ bội số nếu hai active cùng dist tới centroid?
- Toggle bật/tắt có cập nhật **mọi Step** của đỉnh và hoàn tác đủ TreeMap/Fenwick?
- Với countWithin, có All[c] và Sub[c][branch] với **cùng hệ khoảng cách từ c**?
- Khi tính countWithin, có dùng `All.countLE(k−d)−Sub.countLE(k−d)` theo từng Step?
- Khi branch=−1 (v=c), có **không trừ Sub**?
- Fenwick có tìm **upper bound** đúng cho điều kiện ≤?
- K âm, tập active rỗng, n=1 và đỉnh tự active có đúng?
- Tất cả cập nhật có nằm trong O(log² n) và có phân tích chi phí build sorting?
- Nếu chỉ có truy vấn dist(u,v), LCA có đơn giản hơn không?
- Nếu có thêm/xóa cạnh hoặc đổi trọng số, có hiểu cấu trúc tiền xử lý phải xây lại/đổi thuật toán?
- Đã đối chiếu với BFS brute-force trên cây nhỏ và các chuỗi toggle ngẫu nhiên chưa?

**Kết luận:** phân rã trọng tâm tách cây thành các thành phần kích thước không quá một nửa, tạo một cây centroid có chiều cao **O(log n)**. Với mỗi đỉnh, lưu khoảng cách tới các centroid tổ tiên và nhánh mà đỉnh thuộc tại từng centroid. Truy vấn **nearest active** lấy min qua các khoảng cách “đi qua centroid”, chính xác nhờ bất đẳng thức tam giác và sự tồn tại một centroid chung nằm trên đường đi của cặp đỉnh tối ưu. Truy vấn **đếm active trong bán kính** dùng **All trừ Sub theo nhánh** để mỗi cặp được tính đúng một lần, có thể thực hiện bằng Fenwick trên các tọa độ khoảng cách đã nén. Bản Java hỗ trợ **toggle**, **nearest** và **countWithin** trong **O(log² n)** mỗi thao tác, sau tiền xử lý **O(n log² n)** và bộ nhớ **O(n log n)**; các bảo đảm này phụ thuộc việc đầu vào là **cây có độ dài cạnh không âm**, và ví dụ sử dụng độ dài cạnh bằng 1.
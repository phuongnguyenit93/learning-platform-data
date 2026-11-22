# Cây tìm kiếm và biểu diễn một lời giải đang xây dựng

## 1. Cây tìm kiếm trong quay lui là gì?

**Quay lui (backtracking)** là kỹ thuật xây dựng lời giải **từng quyết định một**, thử những lựa chọn còn hợp lệ, đi sâu vào trạng thái mới và **hoàn tác** để thử nhánh khác. Quá trình ấy được mô hình hóa bằng **cây tìm kiếm (search tree)**: mỗi nút thể hiện một trạng thái lời giải **đang xây dựng**, còn mỗi cạnh là một lựa chọn.

Một lời giải hoàn chỉnh không nhất thiết xuất hiện tại mọi nút. Nhiều nút chỉ mô tả **lời giải từng phần (partial solution)**: chẳng hạn “đã chọn ba phần tử đầu trong một bài tổ hợp”, “đã đặt quân hậu ở hai hàng đầu” hoặc “đã đi qua bốn đỉnh của một đường đi”.

Bốn thành phần quan trọng nhất:

1. **Trạng thái:** biểu diễn những quyết định đã chốt và các thông tin cần thiết để xét quyết định tiếp theo.
2. **Ứng viên:** các lựa chọn có thể thử từ trạng thái hiện tại.
3. **Ràng buộc:** quy tắc loại bỏ ngay những lựa chọn sai hoặc không thể dẫn tới đáp án.
4. **Hoàn tác:** khôi phục chính xác trạng thái trước khi thử ứng viên khác.

Cây này thường là **cây khái niệm**. Chương trình không cần cấp phát đối tượng cho từng nút: một lời gọi đệ quy cùng bộ biến trạng thái và thao tác chọn/hoàn tác đã đủ để duyệt cây theo chiều sâu.

Ví dụ chọn tập con từ a=[2,3] để đạt tổng 5. Tại mỗi vị trí có hai quyết định: **lấy** hoặc **bỏ**:

~~~text
                            index=0, sum=0, chosen=[]
                             /                   \
                           lay 2                bo 2
                           /                       \
                  index=1, sum=2              index=1, sum=0
                    /       \                    /       \
                 lay 3      bo 3              lay 3      bo 3
                  /           \                  /           \
              sum=5         sum=2            sum=3         sum=0
              [0,1]          [0]               [1]           []
              DUNG          sai               sai           sai
~~~

Nút có tổng 5 chứa **một nghiệm hoàn chỉnh**: lấy các phần tử ở chỉ số 0 và 1. Các nút khác không thỏa mục tiêu. Trên cây lớn, thay vì vẽ toàn bộ các nút, chương trình duyệt bằng DFS và loại bỏ những nhánh không cần thiết.

**Lưu ý:** quay lui là chiến lược **duyệt không gian lựa chọn có hoàn tác**, không phải cứ có đệ quy là quay lui. Một hàm tính giai thừa tự gọi lại nó không đang thử nhiều ứng viên và không cần phục hồi trạng thái để xét nhánh anh em.

## 2. Đọc cây tìm kiếm: gốc, nút, cạnh, mức và lá

Cấu trúc cây cần được hiểu theo nghĩa thuật toán:

| Thành phần | Ý nghĩa | Ví dụ chọn/bỏ phần tử |
| --- | --- | --- |
| Gốc (root) | Chưa đưa ra quyết định nào | index=0, chosen=[], sum=0 |
| Nút (node) | Một cấu hình lời giải từng phần | Đã xét 2 phần tử, chọn chỉ số [0] |
| Cạnh (edge) | Một quyết định từ trạng thái cha | “Lấy phần tử chỉ số 2” |
| Độ sâu (depth) | Số quyết định đã thực hiện | Độ sâu i ứng với đã xét i phần tử |
| Nhánh (branch) | Hướng lựa chọn có thể thử | Lấy hoặc bỏ |
| Lá (leaf) | Không còn quyết định để thử hoặc dừng sớm | i=n, hoặc đã đạt mục tiêu |
| Nút nghiệm | Trạng thái được quy tắc đích chấp nhận | sum=target |
| Nhánh bị cắt | Không cần xét phần tiếp theo | sum>target khi mọi a[i]>0 |

Cây tìm kiếm **không nhất thiết là cây nhị phân**. Với sinh hoán vị, ở mức đầu có n phần tử để chọn, tiếp theo n-1, rồi n-2; cây có độ phân nhánh thay đổi. Với bài **N quân hậu**, mỗi hàng có thể thử nhiều cột, nhưng những cột xung đột sẽ không tạo nhánh đệ quy.

**Độ sâu tối đa** thường gắn với số quyết định. Với chọn/bỏ n phần tử, độ sâu tối đa n. Với đặt một quân hậu mỗi hàng, độ sâu tối đa n. Tuy nhiên, **số nút** có thể tăng rất nhanh theo độ sâu dù stack chỉ sâu O(n).

### Đếm số nút lý thuyết trước khi cắt nhánh

Nếu có n quyết định nhị phân độc lập và mọi nhánh đều được mở đến độ sâu n:

~~~text
So nut o do sau i = 2^i
So la             = 2^n
Tong so nut       = 1 + 2 + ... + 2^n = 2^(n+1)-1
~~~

Nếu ở mức i có tối đa n-i lựa chọn chưa dùng, số lá hoán vị n phần tử là n!, tổng số nút bị chặn bởi tổng các số chỉnh hợp P(n,i). Đây là **kích thước không gian tìm kiếm**, không phải luôn là số nút thực tế đã thăm: pruning có thể làm số nút nhỏ đi nhiều.

**Cây khái niệm và đồ thị trạng thái khác nhau:** hai đường quyết định khác nhau có thể dẫn đến cùng một bộ giá trị tóm tắt (ví dụ cùng index và sum). Trong bài **đếm hoặc liệt kê nghiệm**, chúng vẫn có thể là **hai cách chọn khác nhau theo chỉ số**. Gộp những trạng thái ấy cần hiểu rõ ta muốn tìm một nghiệm, đếm nghiệm hay liệt kê tất cả.

## 3. Biểu diễn một lời giải đang xây dựng cần những gì?

Thiết kế trạng thái tốt có hai phần:

- **Phần đường đi:** những quyết định đã chọn, thường là mảng/list path, visited[] hoặc mảng gán từng vị trí.
- **Thông tin tóm tắt:** những giá trị hỗ trợ kiểm tra nhánh nhanh, chẳng hạn tổng hiện tại, số phần tử đã chọn, bitmask tập đã dùng hoặc các cờ xung đột.

Một trạng thái tốt phải trả lời được ba câu hỏi:

1. **Đã quyết định những gì?** Ví dụ đã xét a[0..i), hoặc đã đặt hậu ở các hàng 0..r-1.
2. **Những quyết định tiếp theo nào hợp lệ?** Ví dụ chỉ số i chưa xét hoặc các cột chưa có hậu.
3. **Khi nào lời giải được chấp nhận?** Ví dụ sum=target, hoặc đã đặt xong n quân hậu.

### Mẫu chọn tập con

Với một mảng a và một target, ta có thể giữ:

~~~text
nextIndex   : phan tu tiep theo can quyet dinh
chosen      : danh sach chi so da lay, theo thu tu tang
currentSum  : tong gia tri tai cac chi so trong chosen
target      : tong can dat, la du lieu bat bien cua bai
~~~

Nếu a=[2,3,5,7], state (nextIndex=2, chosen=[0,1], currentSum=5) có nghĩa là đã xét hai phần tử đầu, chọn cả hai, và còn các phần tử ở chỉ số 2,3 chưa quyết định. Nếu target=10, ta vẫn có thể lấy a[2]=5. Nếu target=5 và mọi phần tử còn lại **dương**, trạng thái này đã tạo một nghiệm, không thể thêm phần tử nào mà vẫn giữ tổng 5.

Không nhất thiết phải tính currentSum bằng cách cộng lại cả chosen ở mỗi nút. Ta có thể **duy trì tăng dần** currentSum khi chọn, trừ đi khi quay lui hoặc truyền sum bằng giá trị mới vào lời gọi con.

### Mẫu hoán vị

Để dựng một hoán vị của n phần tử phân biệt:

~~~text
path       : cac chi so da chon theo thu tu
used[i]    : true neu chi so i da xuat hien trong path
depth      : do dai path
~~~

Mỗi bước chọn một i chưa used, đánh dấu used[i]=true, thêm i vào path; khi trở về, bỏ i khỏi path và đặt used[i]=false. Bất biến: **mỗi chỉ số xuất hiện tối đa một lần**. Nếu chỉ dùng path mà không kiểm tra used, cùng một phần tử có thể bị chọn lặp, tạo chuỗi không phải hoán vị.

### Mẫu N quân hậu

Nếu đặt một quân hậu trên mỗi hàng của bàn n×n:

~~~text
row           : hang tiep theo can dat quan
placement[r]  : cot dat quan o hang r, neu da dat
usedCol[c]    : cot c da co quan hay chua
usedDiagA[d]  : duong cheo row-col+n-1 da co quan
usedDiagB[d]  : duong cheo row+col da co quan
~~~

Để quyết định đặt ở (row,col), chỉ cần kiểm tra ba mảng xung đột. Không cần quét toàn bộ bàn cờ ở mỗi bước. Bất biến đảm bảo mọi quân ở các hàng đã quyết định đều không tấn công nhau.

**Đừng lưu quá nhiều mà không cần:** nếu sum có thể tính từ path nhưng truy cập thường xuyên, lưu sum giúp kiểm tra O(1); nếu một biến hoàn toàn suy ra được từ một biến khác và không giúp giảm chi phí, có thể bỏ nó để tránh trạng thái mâu thuẫn.

## 4. Chu trình chọn – đi sâu – hoàn tác

Một khung backtracking thường có cấu trúc:

~~~text
search(state):
    if isCompleteAndValid(state):
        recordSolution(copyOfPath)
        return

    if cannotLeadToSolution(state):
        return

    for choice in candidates(state):
        if violatesLocalConstraints(choice, state):
            continue

        apply(choice, state)
        search(nextState)
        undo(choice, state)
~~~

**Chọn (apply):** cập nhật trạng thái như push một phần tử vào path, đánh dấu used hoặc tăng tổng.

**Đi sâu (search):** xử lý những quyết định tiếp theo trên trạng thái vừa tạo.

**Hoàn tác (undo):** đảo đúng mọi thay đổi ở apply, để khi vòng for xét ứng viên kế tiếp, trạng thái trở về đúng như trước khi thử nhánh trước.

**Ghi nghiệm:** thường phải tạo **bản sao** của path ở thời điểm nghiệm hợp lệ. Nếu chỉ lưu tham chiếu đến cùng một ArrayList rồi tiếp tục add/remove, tất cả nghiệm đã lưu có thể đổi theo trạng thái chung, cuối cùng trở thành rỗng hoặc giống nhau.

### Vì sao hoàn tác là bắt buộc khi chia sẻ trạng thái?

Giả sử path ban đầu là [0]. Ta thử thêm 1, gọi search cho path=[0,1], sau đó quay về. Nếu **quên remove(1)**, nhánh kế tiếp thêm 2 sẽ thấy path=[0,1,2] thay vì [0,2]. Khi ấy cây tìm kiếm được duyệt không còn tương ứng với bài toán ban đầu: nhánh anh em bị lẫn quyết định của nhau.

Tương tự, nếu dùng used[] cho hoán vị mà quên đặt lại used[i]=false, một lựa chọn đã thử ở nhánh trước sẽ bị xem là đã dùng trong mọi nhánh sau, làm mất nghiệm hợp lệ.

### Hai cách quản lý trạng thái

- **Biến đổi tại chỗ + hoàn tác:** hiệu quả bộ nhớ, phổ biến trong backtracking; ví dụ ArrayList, boolean[] và đặt lại cờ.
- **Truyền bản sao/bất biến:** mỗi lời gọi con nhận một trạng thái mới; ít nguy cơ rò rỉ thay đổi giữa nhánh nhưng tăng cấp phát và chi phí sao chép.

Có thể kết hợp: truyền **giá trị nguyên thủy** như index, sum bằng tham số mới; chỉ hoàn tác những cấu trúc mutable như path hoặc used[]. Đó là cách được dùng trong ví dụ Java bên dưới.

**Nguyên tắc cốt lõi:** sau khi lời gọi đệ quy trả về và undo hoàn tất, cha phải có **cùng trạng thái quan sát được** như ngay trước khi apply, trừ vùng kết quả đầu ra được chủ ý ghi thêm nghiệm.

## 5. Điểm dừng, nghiệm đầy đủ và trạng thái không thể tiếp tục

Không có một quy tắc base case chung cho mọi bài. Cần phân biệt:

1. **Nghiệm hoàn chỉnh:** các ràng buộc và điều kiện đích đã đạt; ghi lại đáp án nếu đang liệt kê.
2. **Hết lựa chọn nhưng không thành công:** đã xét hết phần tử/hàng/vị trí mà chưa đạt mục tiêu; trở về không ghi nghiệm.
3. **Nhánh chắc chắn bất khả thi:** cắt trước khi tới lá sâu nhất nếu có chứng minh rằng không thể có nghiệm nào dưới nhánh.
4. **Đã đủ mục tiêu tìm kiếm:** nếu chỉ cần **một** nghiệm, có thể dừng toàn bộ tìm kiếm ngay sau khi thấy nó; nếu phải **liệt kê tất cả**, không được dừng ở nghiệm đầu tiên.

Ví dụ chọn tập con có **giá trị dương** và target≥0:

~~~text
if currentSum == target:
    record copy of chosen
    return

if nextIndex == n:
    return
~~~

Vì mọi phần tử còn lại dương, sau khi đạt target, thêm bất kỳ phần tử nào cũng làm tổng vượt target. Do đó có thể ghi nghiệm và dừng nhánh tại đây, kể cả khi chưa xét hết n vị trí.

Nhưng nếu a chứa **số 0**, giả định đó không còn đúng: khi đạt target vẫn có thể chọn thêm một phần tử 0 mà không đổi tổng, tạo **một tập chỉ số khác**. Nếu mục tiêu đếm hoặc liệt kê **mọi tập con theo chỉ số**, dừng sớm tại sum==target sẽ làm mất nghiệm có thêm các số 0. Khi ấy phải tiếp tục duyệt, hoặc gộp số cách của các phần tử 0 còn lại theo công thức đã chứng minh.

Nếu a có **số âm**, tổng hiện tại đã vượt target cũng có thể giảm về target về sau; không được cắt bằng quy tắc “sum>target” của bài số dương.

**Điểm dừng là một phần của chứng minh tính đúng**, không đơn thuần là câu lệnh chống tràn stack.

## 6. Pruning: cắt nhánh đúng và cắt nhánh sai

**Cắt nhánh (pruning)** là việc bỏ qua một cây con khi có bằng chứng rằng **không nghiệm hợp lệ nào** nằm dưới nó. Pruning giúp giảm công việc thực tế, nhưng chỉ **đúng** nếu điều kiện cắt bảo toàn tất cả nghiệm cần tìm.

### Ràng buộc cục bộ

Trong N quân hậu, nếu đặt một quân ở cột đã bị chiếm hoặc đường chéo đã có quân, trạng thái vừa tạo không thể là tiền tố của một nghiệm hợp lệ. Có thể loại **ngay trước khi gọi đệ quy**, vì các quân đã đặt không bị di chuyển về sau trong nhánh ấy.

Trong hoán vị, nếu used[i]=true, không được chọn i lần nữa. Đây là pruning theo ràng buộc “mỗi phần tử chỉ dùng một lần”, hoàn toàn an toàn.

### Cận dưới/cận trên trên tổng

Trong bài tập con với **mọi giá trị dương** và sum đang có:

- Nếu sum>target, mọi phần tử thêm vào chỉ làm sum lớn hơn; cắt.
- Gọi suffix[i] là tổng các phần tử a[i]...a[n-1] còn lại. Nếu sum+suffix[i]<target, ngay cả lấy **tất cả** phần tử còn lại cũng không đủ; cắt.
- Nếu sum==target, có thể ghi nghiệm và dừng như đã chứng minh ở phần trước.

~~~text
suffix[n] = 0
suffix[i] = suffix[i+1] + a[i]

if sum > target:                   prune
if sum + suffix[nextIndex] < target: prune
~~~

**Giả thiết cần nêu:** các a[i]>0; nếu có số âm, cả hai kiểm tra có thể sai. Với số 0, cận suffix vẫn có thể đúng cho khả năng đạt target nhưng **dừng ngay khi đạt target** không đúng nếu muốn đếm mọi tập chỉ số.

Đối với một bài **tối ưu hóa**, nhánh-cận (branch and bound) có thể cắt khi cận trên tốt nhất của cây con **không vượt** nghiệm tối ưu đã biết. Nhưng cận trên phải đúng cho **mọi phần tiếp theo**, không thể dùng một dự đoán cảm tính.

### Không phải cứ ít nhánh là đúng

Ví dụ n=4, a=[2,3,5,7], target=10. Nếu một heuristic luôn thử “lấy phần tử nhỏ trước” rồi **không thử nhánh bỏ**, ta có thể tìm được [2,3,5] nhưng sẽ bỏ sót nghiệm [3,7]. Một heuristic tốt có thể **ưu tiên thứ tự** nhánh để gặp nghiệm sớm; nó **không có quyền xóa nhánh** nếu chưa chứng minh nhánh ấy vô ích đối với mục tiêu tìm kiếm.

Nếu đề hỏi **một** nghiệm, dừng sau [2,3,5] có thể hợp lệ. Nếu đề hỏi **tất cả** nghiệm, phải tiếp tục cho đến khi đã xét mọi nhánh chưa bị loại an toàn.

## 7. DFS, thứ tự duyệt và cấu trúc ngăn xếp

Backtracking thường dùng **depth-first search (DFS)** trên cây quyết định. Khi vào một nút, chương trình thử một ứng viên, đi sâu hết nhánh đó rồi quay lại thử ứng viên tiếp theo.

Ví dụ chọn/bỏ n phần tử theo thứ tự **lấy trước, bỏ sau**:

~~~text
dfs(i, sum, path):
    if solution:
        record path
        return
    if impossible:
        return

    path.add(i)           // Lay phan tu i.
    dfs(i+1, sum+a[i], path)
    path.removeLast()     // Hoan tac.

    dfs(i+1, sum, path)   // Bo phan tu i.
~~~

Đây là giả mã. Java ArrayList có thể dùng remove(path.size()-1) để xóa cuối; chương trình Java 17 bên dưới dùng lệnh đó.

**Thứ tự duyệt quyết định thứ tự tìm thấy nghiệm**, không nhất thiết quyết định nghiệm nào đúng hay tối ưu. Với target=10, a=[2,3,5,7] và lấy trước, kết quả được ghi theo thứ tự:

~~~text
[0,1,2]   -> gia tri [2,3,5], tong 10
[1,3]     -> gia tri [3,7], tong 10
~~~

Nếu chọn bỏ trước, thứ tự nghiệm có thể đảo. Nếu đổi cách sắp phần tử, **chỉ số và thứ tự in** cũng có thể thay đổi; phải nói rõ trả chỉ số mảng gốc hay mảng đã sắp.

### Stack và bộ nhớ

Mỗi lời gọi đệ quy giữ index, tổng, vị trí quay về và biến cục bộ của mức ấy. Nếu độ sâu tối đa n thì ngăn xếp đệ quy thường O(n); path có tối đa n phần tử. Không cần cấp phát toàn bộ cây có 2^n nút.

Nếu n cực lớn, đệ quy sâu có thể gây **StackOverflowError** trong Java; có thể mô phỏng DFS bằng một stack chứa các frame với trạng thái chọn/đang quay lui. Nhưng mô phỏng phải giữ đủ thông tin “đã thử ứng viên nào”, không thể chỉ lưu một chỉ số.

### Tìm một nghiệm, đếm hay liệt kê

- **Tìm một nghiệm:** có thể trả boolean hoặc một path rồi dừng ngay khi thấy nghiệm đầu. Một nhánh chứa nghiệm đủ cho yêu cầu.
- **Đếm nghiệm:** tăng bộ đếm khi gặp nghiệm; có thể dùng memoization/DP trên trạng thái nếu bài toán có trạng thái trùng nhau và không cần liệt kê đường đi cụ thể.
- **Liệt kê mọi nghiệm:** sao chép path ở mỗi nút nghiệm; chi phí đầu ra phụ thuộc vào số nghiệm và có thể rất lớn.
- **Tối ưu hóa:** duy trì best và cận, hoặc dùng kỹ thuật khác nếu không gian tìm kiếm quá lớn.

Chọn đúng mục tiêu ngay từ đầu giúp xác định thời điểm dừng và có được phép gộp trạng thái hay không.

## 8. Ví dụ Java 17 số 1: cây chọn/bỏ để tìm các tập con theo tổng

Bài toán: cho một mảng số nguyên **dương** a và một tổng target≥0, hãy liệt kê **mọi tập con theo chỉ số** có tổng đúng target, mỗi phần tử được dùng tối đa một lần.

Ví dụ a=[2,3,5,7], target=10 có hai lời giải [0,1,2] và [1,3]. Ta chọn **lấy trước, bỏ sau**, nên thứ tự trả lời ổn định theo cây DFS.

Trạng thái được biểu diễn bằng:

- index: phần tử đầu tiên chưa quyết định.
- sum: tổng giá trị của các chỉ số đã chọn.
- chosen: danh sách chỉ số đã chọn theo thứ tự tăng.
- suffix[index]: tổng tất cả giá trị còn lại để dùng làm cận trên khả năng đạt target.
- answers: nơi tích lũy các bản sao nghiệm; nó **không được hoàn tác**.

### Tại sao phải kiểm tra a[i]>0?

Mã này dùng cả hai pruning sum>target, sum+suffix[index]<target và dừng ngay khi sum==target. Để cả ba an toàn khi **liệt kê mọi tập chỉ số**, ta ràng buộc giá trị phần tử **nghiêm ngặt dương**. Nếu đầu vào có 0 hoặc âm, chương trình **từ chối**; muốn hỗ trợ chúng phải thiết kế lại điều kiện dừng/pruning.

Với a=[], target=0, có đúng **một** tập chỉ số đạt tổng 0: tập rỗng []. Vì thế danh sách tất cả nghiệm là **[[]]**, không phải danh sách rỗng. Với a=[], target>0, không có nghiệm, kết quả là [].

Trong mã chạy độc lập ở phần tiếp theo, hàm subsetsByTarget thực hiện đúng hợp đồng ấy.

## 9. Ví dụ Java 17 số 2: cây đặt N quân hậu

Bài toán N-Queens: đặt n quân hậu trên bàn cờ n×n sao cho **không có hai quân nào cùng hàng, cột hoặc đường chéo**. Mỗi lời giải được biểu diễn bằng một danh sách dài n:

~~~text
placement[row] = column

n = 4
[1,3,0,2]  nghia la:
    quan tai (0,1)
    quan tai (1,3)
    quan tai (2,0)
    quan tai (3,2)
~~~

Ở đây chỉ số hàng/cột đều bắt đầu từ 0. Thay vì thử mọi ô trong bàn cờ, ta chọn **chính xác một cột cho mỗi hàng**, nên mọi lời giải từng phần tự động không có hai quân cùng hàng.

Các mảng Boolean duy trì thông tin xung đột:

~~~text
column[c]                   : co quan o cot c
diagDiff[row-col+n-1]       : co quan tren duong cheo /
diagSum[row+col]            : co quan tren duong cheo \
~~~

Tên hướng dấu chéo có thể khác trong tài liệu; quan trọng là **hai quân cùng đường chéo khi có cùng row-col hoặc cùng row+col**. Chỉ số row-col+n-1 nằm trong [0,2n-2]; row+col cũng vậy. Hai mảng đường chéo cần độ dài 2n-1.

Ở hàng row, thử c từ 0 đến n-1. Nếu cả ba cờ đều false:

1. Đặt placement[row]=c.
2. Đánh dấu column[c], diagDiff[d1], diagSum[d2] thành true.
3. Gọi tìm kiếm cho row+1.
4. Sau khi quay về, **gỡ cờ và xóa placement[row]** để thử cột khác.

Nếu row==n, ta đã đặt đủ n quân, các ràng buộc được duy trì từ đầu, nên đó là một nghiệm hợp lệ; sao chép placement và lưu lại.

Với n=4, có đúng hai nghiệm:

~~~text
[1,3,0,2]
[2,0,3,1]
~~~

Với n=2 hoặc n=3, không có nghiệm. Trong ví dụ Java, n được giới hạn từ 1 đến 12 để tránh vô ý cấp phát danh sách nghiệm khổng lồ; đây là **giới hạn minh họa**, không phải giới hạn toán học của N-Queens.

## 10. Chương trình Java 17 hoàn chỉnh: hai dạng cây tìm kiếm

Ví dụ bên dưới kết hợp cả cây **nhị phân lấy/bỏ** và cây **nhiều nhánh đặt hậu theo hàng** vào một tệp Java duy nhất. Các phương thức trả danh sách nghiệm thay vì chỉ in khi tìm được, giúp người dùng kiểm thử và tái sử dụng kết quả.

Lưu dưới tên **BacktrackingSearchTreeDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class BacktrackingSearchTreeDemo {

    // Liet ke cac TAP CHI SO, voi moi a[i] > 0 va target >= 0.
    static List<List<Integer>> subsetsByTarget(int[] a, long target) {
        Objects.requireNonNull(a, "a");
        if (target < 0) {
            throw new IllegalArgumentException("target must be nonnegative");
        }
        for (int x : a) {
            if (x <= 0) {
                throw new IllegalArgumentException(
                        "all values must be positive");
            }
        }

        long[] suffix = new long[a.length + 1];
        for (int i = a.length - 1; i >= 0; i--) {
            suffix[i] = suffix[i + 1] + a[i];
        }

        List<List<Integer>> answers = new ArrayList<>();
        dfsSubset(0, 0L, target, a, suffix,
                new ArrayList<>(), answers);
        return List.copyOf(answers);
    }

    private static void dfsSubset(
            int index, long sum, long target,
            int[] a, long[] suffix,
            List<Integer> chosen, List<List<Integer>> answers) {

        // An toan vi cac gia tri CHI co the duong.
        if (sum == target) {
            answers.add(List.copyOf(chosen));
            return;
        }
        if (index == a.length || sum > target
                || sum + suffix[index] < target) {
            return;
        }

        // Nhanh 1: lay phan tu tai index.
        chosen.add(index);
        dfsSubset(index + 1, sum + a[index], target,
                a, suffix, chosen, answers);
        chosen.remove(chosen.size() - 1); // Hoan tac.

        // Nhanh 2: bo phan tu tai index.
        dfsSubset(index + 1, sum, target,
                a, suffix, chosen, answers);
    }

    // Moi ket qua: cot cua quan hau o tung hang.
    static List<List<Integer>> solveQueens(int n) {
        if (n < 1 || n > 12) {
            throw new IllegalArgumentException("n must be in [1,12]");
        }
        boolean[] usedColumn = new boolean[n];
        boolean[] usedDiagDiff = new boolean[2 * n - 1];
        boolean[] usedDiagSum = new boolean[2 * n - 1];
        int[] placement = new int[n];
        Arrays.fill(placement, -1);

        List<List<Integer>> answers = new ArrayList<>();
        dfsQueens(0, n, usedColumn, usedDiagDiff,
                usedDiagSum, placement, answers);
        return List.copyOf(answers);
    }

    private static void dfsQueens(
            int row, int n,
            boolean[] usedColumn, boolean[] usedDiagDiff,
            boolean[] usedDiagSum, int[] placement,
            List<List<Integer>> answers) {

        if (row == n) {
            List<Integer> solution = new ArrayList<>(n);
            for (int col : placement) {
                solution.add(col);
            }
            answers.add(List.copyOf(solution));
            return;
        }

        for (int col = 0; col < n; col++) {
            int d1 = row - col + n - 1;
            int d2 = row + col;
            if (usedColumn[col] || usedDiagDiff[d1]
                    || usedDiagSum[d2]) {
                continue;
            }

            // Chon.
            placement[row] = col;
            usedColumn[col] = true;
            usedDiagDiff[d1] = true;
            usedDiagSum[d2] = true;

            // Di sau.
            dfsQueens(row + 1, n, usedColumn, usedDiagDiff,
                    usedDiagSum, placement, answers);

            // Hoan tac day du de thu cot tiep theo.
            usedColumn[col] = false;
            usedDiagDiff[d1] = false;
            usedDiagSum[d2] = false;
            placement[row] = -1;
        }
    }

    public static void main(String[] args) {
        int[] values = {2, 3, 5, 7};

        System.out.println("subsets target 10 = " +
                subsetsByTarget(values, 10));
        System.out.println("subsets target 1 = " +
                subsetsByTarget(values, 1));
        System.out.println("empty target zero = " +
                subsetsByTarget(new int[0], 0));

        System.out.println("queens n=4 = " + solveQueens(4));
        System.out.println("queens n=2 = " + solveQueens(2));

        try {
            subsetsByTarget(new int[]{2, 0}, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid subset input: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac BacktrackingSearchTreeDemo.java
java BacktrackingSearchTreeDemo
~~~

**Stdout chính xác:**

~~~text
subsets target 10 = [[0, 1, 2], [1, 3]]
subsets target 1 = []
empty target zero = [[]]
queens n=4 = [[1, 3, 0, 2], [2, 0, 3, 1]]
queens n=2 = []
invalid subset input: all values must be positive
~~~

### Giải thích mã chọn tập con

**subsetsByTarget:** xác minh mảng không null, target≥0 và mọi giá trị dương. Nó xây suffix từ phải sang trái bằng long để tổng nhiều int không bị tràn int. Với mảng int[] hợp lệ, tổng các int dương không vượt giới hạn long. Hàm không sắp xếp hay sửa input, nên những chỉ số trong kết quả chính là chỉ số gốc.

**dfsSubset:** trước hết kiểm tra đã đạt target hay chưa. Vì giá trị còn lại đều dương, nếu đạt target thì ghi **bản sao bất biến của chosen** và dừng; không cần đưa thêm phần tử. Nếu đã hết phần tử, tổng vượt target hoặc sum+suffix[index]<target, nhánh không thể tạo nghiệm.

Khi xét một index, nhánh lấy thêm index vào chosen, gọi đệ quy với sum+a[index], rồi remove phần tử cuối để khôi phục chosen. Nhánh bỏ không sửa chosen, chỉ tăng index. Do đó **mỗi tập chỉ số được tạo theo một chuỗi quyết định duy nhất**, không sử dụng lại phần tử nào.

**List.copyOf(chosen)** cực kỳ quan trọng: nó tạo một danh sách mới với các phần tử hiện tại. Nếu answers.add(chosen) thay cho sao chép, mọi nghiệm có thể cùng trỏ đến danh sách chosen đang thay đổi, dẫn đến sai kết quả sau backtracking.

### Giải thích mã N quân hậu

**solveQueens:** mỗi lời giải là một danh sách n cột. Các mảng cột và đường chéo đều ban đầu false; placement được gán -1 cho những hàng chưa đặt. Mã kiểm tra giới hạn n vì liệt kê toàn bộ nghiệm có thể tốn rất nhiều bộ nhớ.

**dfsQueens:** thử cột theo thứ tự 0..n-1. Cột/đường chéo xung đột bị bỏ qua trước khi đặt quân. Với cột hợp lệ, đánh dấu ba cờ, gán placement[row], đệ quy sang hàng sau; khi quay về, xóa đúng ba cờ và khôi phục placement[row]=-1.

Các mảng này là **trạng thái chia sẻ có hoàn tác** giữa các mức. Trạng thái nghiệm được tạo thành một List mới trước khi lưu, nên các phép hoàn tác không ảnh hưởng tới nghiệm đã ghi.

### Độ phức tạp

| Bài | Số nhánh/mức | Thời gian trường hợp xấu | Bộ nhớ làm việc ngoài kết quả |
| --- | --- | --- | --- |
| Chọn/bỏ n phần tử, chưa tính pruning | 2 lựa chọn mỗi mức | O(n×2^n) nếu sao chép mỗi nghiệm dài tới n; phần duyệt cây là O(2^n) | O(n) stack/path/suffix |
| Hoán vị n phần tử | n,n-1,... | O(n×n!) khi sinh và sao chép n phần tử cho mỗi nghiệm | O(n) stack/path/used |
| N quân hậu với kiểm tra O(1) | Tối đa n cột mỗi hàng, bị giảm do xung đột | Có thể chặn thô O(n×n!) lượt kiểm tra ứng viên; chi phí lưu nghiệm cộng thêm | O(n) stack/placement/cờ |
 
**Chi phí lưu đầu ra:** nếu có S nghiệm, mỗi nghiệm chứa tối đa n chỉ số, danh sách kết quả có thể cần O(S×n) bộ nhớ. Giới hạn này **không nằm** trong O(n) bộ nhớ làm việc đã nêu. Nếu chỉ cần đếm thay vì lưu, có thể giảm bộ nhớ đầu ra bằng cách tăng bộ đếm khi đến nghiệm, nhưng số lần duyệt vẫn có thể lớn.

Các cận trên là đánh giá trường hợp xấu, không phải dự đoán chính xác số nút sau pruning. Với phần tử dương và target nhỏ, hai cận sum>target và sum+suffix<target có thể cắt nhiều nhánh, nhưng không làm thuật toán trở thành đa thức cho mọi đầu vào.

## 11. Chứng minh tính đúng của cây và DFS

Cần chứng minh cả ba việc: **mọi lời giải in ra đều hợp lệ (soundness)**, **không bỏ sót lời giải (completeness)** và **không liệt kê trùng đường quyết định (uniqueness)**, trừ khi đề cho phép trùng.

### Trường hợp chọn tập con

**Bất biến:** trong lời gọi dfsSubset(index,sum,...), chosen chỉ chứa các chỉ số tăng nghiêm ngặt trong [0,index), và sum bằng tổng a[j] với j thuộc chosen. Các phần tử ở vị trí index..n-1 chưa được quyết định.

- **Cơ sở:** ở lời gọi gốc index=0, chosen rỗng và sum=0, nên bất biến đúng.
- **Bước nhánh lấy:** thêm index làm chosen vẫn tăng vì mọi chỉ số trước nhỏ hơn index; tăng sum theo a[index], gọi với index+1, nên bất biến giữ.
- **Bước nhánh bỏ:** không thêm index và tăng index, nên bất biến giữ.
- **Hoàn tác:** remove phần tử vừa thêm đưa chosen về đúng giá trị trước nhánh lấy; nhánh bỏ được bắt đầu trên trạng thái cha nguyên vẹn.

**Soundness:** chỉ ghi chosen khi sum=target; bất biến đảm bảo các chỉ số không trùng, đều hợp lệ và tổng đúng target.

**Completeness:** với một tập chỉ số hợp lệ bất kỳ, ở mỗi index nó hoặc chứa index (đi nhánh lấy) hoặc không (đi nhánh bỏ). Chuỗi quyết định duy nhất ấy được cây DFS thử, trừ khi bị pruning. Do mọi phần tử dương, sum>target không thể sửa bằng phần còn lại; sum+suffix[index]<target cũng không thể đạt target; đạt sum==target thì không thể thêm phần tử dương nào khác để vẫn đạt target. Vậy không pruning nào bỏ mất nghiệm.

**Uniqueness:** một tập chỉ số xác định chính xác một quyết định lấy/bỏ tại từng index, nên không có hai đường khác nhau tạo cùng **tập chỉ số**. Nếu hai chỉ số chứa cùng giá trị, hai tập chỉ số khác nhau vẫn được tính riêng đúng theo hợp đồng.

### Trường hợp N quân hậu

**Bất biến:** khi dfsQueens(row,...) được gọi, mỗi hàng 0..row-1 có đúng một quân, không có hai quân trùng cột hoặc cùng đường chéo, và các mảng used phản ánh chính xác các quân ấy.

- Ban đầu row=0 không có quân, bất biến hiển nhiên đúng.
- Khi thử cột col, kiểm tra cột và cả hai đường chéo đảm bảo quân mới không xung đột với quân cũ; hàng mới chưa có quân do chỉ đặt một quân mỗi lời gọi.
- Hoàn tác xóa đúng đánh dấu của quân mới, trả các mảng về trạng thái trước khi thử col.
- Khi row=n, đã đặt n quân ở n hàng khác nhau và không có xung đột, nên lưu một lời giải hợp lệ.
- Mọi cách đặt n quân hợp lệ có đúng một cột ở mỗi hàng; DFS thử cột ấy, và vì nó không xung đột nên không bị bỏ. Do đó không bỏ sót.

**Không phụ thuộc vào “may mắn” của ví dụ:** chứng minh dựa trên cấu trúc cây, bất biến và điều kiện cắt, nên áp dụng cho mọi n nằm trong miền mà chương trình thực thi đầy đủ.

## 12. Khi có giá trị trùng nhau: tránh nghiệm trùng hay giữ theo chỉ số?

Với a=[2,2,3], lựa chọn chỉ số [0,2] và [1,2] đều tạo tổng 5, nhưng có cùng **đa tập giá trị** {2,3}. Phải xác định đề bài yêu cầu gì:

- **Đếm/liệt kê các bộ chỉ số:** đây là **hai nghiệm khác nhau**; không được tự ý khử trùng.
- **Đếm/liệt kê các tổ hợp giá trị không phân biệt chỉ số:** hai nghiệm ấy nên được gộp thành **một** tổ hợp. Cần một quy tắc sinh chuẩn tắc (canonical generation) hoặc một tập kết quả có quy tắc equality rõ ràng.

Với bài tổ hợp giá trị, cách phổ biến là **sắp xếp dữ liệu** rồi, tại cùng một độ sâu, bỏ qua các giá trị trùng đã thử:

~~~text
for i from start to n-1:
    if i > start and values[i] == values[i-1]:
        continue    // Chi bo trung O CUNG MUC.
    choose values[i]
    search(i+1)
    undo
~~~

Điều kiện i>start là mấu chốt. Nếu cứ bỏ mọi phần tử bằng giá trị phần tử trước ở **mọi độ sâu**, ta có thể đánh mất những tổ hợp có hai số bằng nhau như [2,2]. Quy tắc khử trùng theo độ sâu cho phép dùng nhiều bản sao ở các mức khác nhau nhưng không tạo cùng một tổ hợp giá trị bằng các nhánh tương đương tại cùng một mức.

**Lưu ý:** đây là giả mã cho mô hình **sinh tổ hợp không phân biệt chỉ số**. Không được áp dụng trực tiếp vào hàm subsetsByTarget ở ví dụ Java vì hàm ấy có hợp đồng **trả tập chỉ số**, và sắp xếp sẽ thay đổi mối liên hệ chỉ số với mảng gốc nếu không lưu mapping.

### Tổ hợp và hoán vị khác nhau

- Tổ hợp không xét thứ tự: dùng start tăng để tránh sinh cả [2,3] lẫn [3,2].
- Hoán vị xét thứ tự: cần dùng used[] và cho phép các vị trí kế tiếp chọn từ nhiều chỉ số chưa dùng.
- Nếu hoán vị có giá trị trùng, có thể cần sắp xếp và quy tắc bỏ trùng khi một bản sao đứng trước chưa được dùng; phải chứng minh quy tắc cho đúng loại kết quả.

Đây là ví dụ cho nguyên tắc lớn: **cây tìm kiếm phải sinh đúng những đối tượng mà đề bài xem là khác nhau**, không phải cứ “một đường đi” là một kết quả khác nhau về mọi tiêu chí.

## 13. Tìm một nghiệm, liệt kê mọi nghiệm và tối ưu: chọn kiểu trả về

Cùng một cây, cách viết hàm thay đổi theo yêu cầu đầu ra.

### Chỉ cần tìm một nghiệm

Có thể viết DFS trả boolean:

~~~text
boolean search(...):
    if completeAndValid:
        save current path
        return true

    for each choice:
        apply(choice)
        if search(nextState):
            undo(choice)  // Neu trang thai se duoc su dung tiep.
            return true
        undo(choice)

    return false
~~~

Nếu cần giữ path của nghiệm cuối thì **không được vừa giữ path để trả về vừa undo nó trước khi sao chép**. Một thiết kế an toàn là sao chép nghiệm khi gặp base case hoặc trả một đối tượng nghiệm bất biến. Nếu có ngoại lệ hoặc dừng sớm, cơ chế hoàn tác nên được thiết kế sao cho mọi lối thoát giữ trạng thái nhất quán, ví dụ sử dụng finally khi thích hợp.

### Đếm số nghiệm

Thay vì answers.add(copy), ta có thể tăng count ở mỗi nút nghiệm. Nhưng nếu cần đếm số lớn hơn long, phải dùng BigInteger hoặc modulo theo yêu cầu.

Nếu trạng thái con lặp lại, một bộ nhớ đệm chứa **số cách hoàn thành từ trạng thái** có thể giúp giảm tính toán. Tuy nhiên, cache key phải chứa mọi ràng buộc ảnh hưởng tương lai. Ví dụ đối với hoán vị, chỉ nhớ depth không đủ vì tập phần tử đã dùng khác nhau sẽ quyết định các ứng viên tiếp theo.

### Tối ưu hóa

Giữ một nghiệm tốt nhất đã biết. Nếu cận trên của bất kỳ cây con nào **không thể vượt best**, có thể cắt nó khi chỉ cần **giá trị tối ưu** hoặc **một nghiệm tối ưu**. Nếu cần **tất cả các nghiệm cùng tối ưu**, cắt ở dấu bằng có thể làm mất nghiệm đồng tối ưu; quy tắc so sánh cận phải thay đổi theo đầu ra.

Đừng lẫn **tối ưu bằng DP** với **quay lui có cận**: cả hai có thể giải một số bài tương tự, nhưng DP tận dụng trạng thái con trùng nhau, còn quay lui thường trực tiếp duyệt các quyết định và cắt nhánh không thể thành công.

## 14. Phân tích độ phức tạp và lựa chọn biểu diễn

Khi phân tích một lời giải quay lui, hãy tách ít nhất bốn thành phần:

1. **Chiều sâu tối đa:** bao nhiêu quyết định cần thực hiện trước khi dừng?
2. **Số ứng viên tại mỗi nút:** tối đa 2, n hay một số phụ thuộc trạng thái?
3. **Chi phí kiểm tra/chuyển trạng thái:** O(1) với cờ/mảng, hay O(n) nếu quét lại dữ liệu?
4. **Chi phí ghi nghiệm:** sao chép path có thể tốn O(n) mỗi nghiệm.

Ví dụ nếu dùng boolean[] used trong hoán vị, kiểm tra một ứng viên O(1), nhưng vòng for vẫn có thể quét n phần tử để tìm ứng viên chưa dùng. Nếu dùng cây tìm kiếm nhiều nhánh mà cứ sao chép toàn bộ path ở mọi bước, bộ nhớ và cấp phát có thể tăng đáng kể; thao tác thêm/xóa tại chỗ thường rẻ hơn khi viết đúng.

**Biểu diễn phần lời giải quyết định cả tốc độ kiểm tra ràng buộc.**

| Bài toán | Biểu diễn đơn giản | Biểu diễn hỗ trợ kiểm tra nhanh |
| --- | --- | --- |
| Tập con | Danh sách chỉ số đã chọn | index, sum, suffix còn lại |
| Hoán vị | Danh sách phần tử đã chọn | used[] hoặc bitmask |
| N quân hậu | Bàn cờ char[][] | placement[] và cờ cột/đường chéo |
| Đường đi trên đồ thị | Danh sách đỉnh đã đi | path cộng visited[] |
| Điền ô theo ràng buộc | Ma trận trạng thái hiện tại | Tập ứng viên/bitset theo hàng, cột, vùng |
| Xâu hợp lệ | Chuỗi prefix | Bộ đếm, ký tự trước, trạng thái automaton |

Bitmask có thể biểu diễn tập phần tử đã dùng rất gọn khi n nhỏ: bit i bằng 1 nếu đã dùng chỉ số i. Khi chuyển, dùng mask | (1<<i); khi kiểm tra dùng (mask & (1<<i)) != 0. Trong Java, kiểu int có 32 bit, nhưng phép dịch theo int dùng số bit thấp của số dịch, nên **không được** dùng (1<<i) với i≥32 và mong tạo bit mới. Với n đủ lớn, dùng long trong giới hạn phù hợp hoặc BitSet/boolean[].

**Tối ưu hóa thứ tự chọn ứng viên (heuristic):** thử lựa chọn hứa hẹn trước có thể tìm một nghiệm nhanh hơn, nhưng nếu phải liệt kê mọi nghiệm thì thường không giảm được việc kiểm tra các nhánh không bị cắt. Thứ tự thử không thay thế cho điều kiện pruning có chứng minh.

### Tại sao backtracking vẫn hữu ích dù trường hợp xấu là hàm mũ?

Nhiều bài toán tổ hợp có không gian nghiệm lớn về bản chất. Nhưng với ràng buộc mạnh, cây thực tế có thể thưa, và khả năng **kiểm tra tính khả thi từng bước** giúp loại một phần lớn nhánh trước khi chúng thành lá. Quay lui cũng cung cấp lời giải cụ thể, thuận tiện khi đề yêu cầu **danh sách cấu hình** chứ không chỉ số lượng.

Giới hạn đầu vào và yêu cầu đầu ra vẫn quyết định tính khả thi. Nếu phải liệt kê 1 triệu nghiệm dài n, riêng việc tạo và in nghiệm đã tốn tài nguyên, cho dù kiểm tra ràng buộc rất nhanh.

## 15. Những lỗi thường gặp

| Lỗi | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Chưa định nghĩa rõ một nút biểu diễn gì | Trạng thái thiếu thông tin, nhánh sai | Viết hợp đồng state trước khi code |
| Không hoàn tác path/used | Nhánh anh em nhận thay đổi của nhau | Áp dụng và đảo chính xác từng thay đổi |
| Lưu tham chiếu mutable thay vì bản sao | Mọi nghiệm thành rỗng hoặc giống nhau | Sao chép path khi ghi nghiệm |
| Base case đặt sai mức | Bỏ sót nghiệm hoặc ghi trạng thái chưa xong | Xác định đúng điều kiện hoàn thành |
| Dừng sớm khi sum==target nhưng còn số 0 | Thiếu tập chỉ số hợp lệ | Chỉ dừng sớm khi còn toàn phần tử dương |
| Cắt sum>target dù có số âm | Bỏ nghiệm mà phần sau bù lại được | Chứng minh pruning theo miền giá trị |
| Dùng một phần tử nhiều lần | Nghiệm không phải tập con/hoán vị | Tăng index hoặc dùng used[] |
| Không đồng bộ used với path | Kiểm tra sai ứng viên | Giữ invariant và undo tương ứng |
| Lấy cùng giá trị là cùng chỉ số | Sai số nghiệm với phần tử trùng | Phân biệt index và value |
| Khử trùng sai độ sâu | Mất các tổ hợp có phần tử bằng nhau | Dùng quy tắc skip chỉ tại cùng mức |
| Không xác định cần một hay mọi nghiệm | Dừng sớm không đúng | Chốt yêu cầu đầu ra trước |
| Đếm/ghi nghiệm ở mọi nút có vẻ tốt | Ghi cả nghiệm chưa hoàn chỉnh | Tách complete khỏi promising |
| Không cập nhật cờ đường chéo | N-Queens nhận nghiệm bị tấn công | Dùng row-col+n-1 và row+col |
| Cập nhật cờ rồi bỏ quên undo khi return | Những nhánh sau bị khóa | Dùng mẫu apply–dfs–undo nhất quán |
| Tin rằng cắt nhánh luôn làm thuật toán đa thức | Dự toán tài nguyên sai | Phân tích worst case riêng |
| Không tính bộ nhớ đầu ra | OOM khi nhiều nghiệm | Phát từng nghiệm qua callback/stream khi phù hợp |
| Dùng mảng bit sai giới hạn n | Dịch bit quấn hoặc tràn | Kiểm tra miền dịch, dùng long/BitSet phù hợp |

**Một phép thử thực dụng:** đặt một assertion rằng path.size() trước và sau khi thử mỗi ứng viên phải bằng nhau, và các cờ used/diag phải được phục hồi. Nếu sai, bug thường nằm ở nhánh return sớm hoặc quên thao tác undo.

## 16. Kiểm thử bằng tính chất và đối chứng

### Với bài tập con theo tổng

- Mỗi danh sách chỉ số phải **tăng nghiêm ngặt**, không có chỉ số lặp và nằm trong [0,n).
- Tổng a[i] theo mỗi nghiệm phải bằng target.
- Không sửa mảng a do người gọi cung cấp.
- Với mọi a[i]>0, target=0 phải có đúng một nghiệm: tập rỗng.
- Nếu tổng tất cả a[i]<target, kết quả rỗng; nếu target<0, API từ chối.
- Nếu có giá trị 0/âm, API minh họa phải từ chối, tránh áp dụng pruning không đúng.
- Các nghiệm không trùng nhau **theo tập chỉ số**.
- Với n nhỏ, duyệt toàn bộ 2^n bitmask và so **tập các bộ chỉ số** với kết quả DFS để kiểm tra đầy đủ; thứ tự xuất có thể phụ thuộc branch order.

### Với N quân hậu

- Mỗi nghiệm phải có đúng n phần tử, mỗi phần tử là một cột trong [0,n).
- Không có hai hàng trùng cột.
- Với mọi cặp hàng r1≠r2, phải có |r1-r2|≠|col[r1]-col[r2]| để không cùng đường chéo.
- Với n=1 có một nghiệm [0].
- Với n=2 và n=3 không có nghiệm.
- Với n=4 có hai nghiệm [1,3,0,2] và [2,0,3,1].
- Nếu cần kiểm tra thêm, n=5 có 10 nghiệm, n=8 có 92 nghiệm; với n lớn hãy cẩn thận chi phí lưu và in.
- Một nghiệm được lưu phải giữ nguyên sau khi DFS quay lui thử các nhánh khác.

### Bộ ca mẫu

| Đầu vào | Kết quả mong đợi |
| --- | --- |
| a=[2,3,5,7], target=10 | Hai tập chỉ số [0,1,2], [1,3] |
| a=[2,3,5,7], target=1 | [] |
| a=[], target=0 | [[]] |
| a=[], target=2 | [] |
| a=[5], target=5 | [[0]] |
| a=[2,2,3], target=5 | [[0,2],[1,2]] theo thứ tự DFS lấy trước |
| a=[2,0], target=2 | Từ chối vì có phần tử không dương |
| a=[-2,3], target=1 | Từ chối vì có phần tử âm |
| N-Queens n=1 | [[0]] |
| N-Queens n=2,3 | [] |
| N-Queens n=4 | Hai nghiệm kể trên |
| N-Queens n=0 hoặc n>12 trong demo | Từ chối theo hợp đồng |

**Đối chứng độc lập:** sinh tất cả tập chỉ số bằng bitmask cho n≤16 (để không vượt thời gian thử nghiệm), cộng giá trị và so với tập kết quả. Với N-Queens nhỏ, kiểm tra lại từng nghiệm bằng so cặp hàng/cột/đường chéo, độc lập với các mảng cờ dùng trong DFS.

Nếu có nhiều nghiệm cùng cấu trúc hoặc giá trị trùng nhau, hãy kiểm thử theo **chỉ số** hoặc theo **giá trị chuẩn tắc** đúng như hợp đồng, không tùy ý so tên chuỗi đã in.

## 17. Bài tập tự luyện

1. Vẽ đầy đủ cây chọn/bỏ của a=[1,2,3], ghi (index,sum,chosen) ở từng nút. Với target=3, liệt kê các đường đi cho nghiệm [0,1] và [2].
2. Trên a=[2,3,5,7], target=10, mô phỏng DFS lấy trước, ghi từng lần add/remove, và chứng minh path luôn được phục hồi trước khi mở nhánh bỏ.
3. Sửa yêu cầu thành **chỉ cần một nghiệm**. Viết hàm trả về Optional<List<Integer>> hoặc boolean kèm bản sao path; bảo đảm mọi lối thoát đều giữ trạng thái đúng.
4. Đổi dữ liệu thành a=[0,2,3], target=5. Chứng minh vì sao dừng ngay ở sum==target mất một tập chỉ số. Sửa base case để liệt kê đầy đủ khi cho phép 0.
5. Đổi dữ liệu thành a=[-4,6,3], target=2. Chỉ ra nhánh có sum>target nhưng vẫn có thể được cứu bởi phần tử âm; thiết kế lại pruning.
6. Với hoán vị các số 1..n, viết trạng thái path+used[] và đếm số lá n!. So sánh số nút trước và sau khi thêm ràng buộc cấm hai phần tử kề nhau bằng nhau.
7. Cho a=[2,2,3], target=5, phân biệt hai nghiệm theo chỉ số và một nghiệm theo đa tập giá trị. Viết quy tắc loại giá trị trùng **tại cùng mức**.
8. Với N=4, vẽ cây thử cột theo từng hàng. Tìm trạng thái đầu tiên phải cắt vì xung đột đường chéo và giải thích d1=row-col+n-1, d2=row+col.
9. Thay việc quét cả bàn cờ để kiểm tra quân hậu bằng usedColumn và hai mảng đường chéo. So sánh chi phí kiểm tra một ứng viên trước/sau.
10. Viết bộ kiểm thử property-based: sau mỗi lần dfs trở về, xác nhận các cờ và path giống hệt snapshot trước nhánh. Thử cố tình bỏ một lệnh undo để nhìn thấy lỗi.
11. Bổ sung bộ đếm visitedNodes và prunedNodes vào chương trình. Trên cùng a,target, đo sự thay đổi số nút khi bật/tắt cận suffix; giải thích vì sao số nút thực tế khác chặn trên lý thuyết.
12. Nếu chỉ cần **đếm** số cách đạt target, so sánh duyệt DFS với DP theo (index,sum). Khi nào có thể memoize số cách mà không làm mất sự phân biệt của các bộ chỉ số?
13. Mô phỏng DFS bằng stack tường minh: mỗi frame chứa depth và ứng viên tiếp theo, kèm thao tác undo tương ứng. Chứng minh kết quả giống với phiên bản đệ quy.
14. Nêu một bài toán mà biến dùng để pruning không đủ thông tin cho quyết định tiếp theo. Hãy bổ sung trạng thái hoặc chứng minh cần mang theo lịch sử nào.

**Kết luận:** cây tìm kiếm là bản đồ các **quyết định**, còn lời giải đang xây dựng là **trạng thái dọc một đường từ gốc tới nút hiện tại**. Quay lui đúng phải giữ bất biến của trạng thái, xét các ứng viên theo hợp đồng, loại nhánh chỉ khi có chứng minh, ghi bản sao nghiệm khi hoàn chỉnh và **hoàn tác đầy đủ** trước nhánh kế tiếp. Thiết kế trạng thái tốt quyết định cả tính đúng, khả năng pruning và hiệu quả của thuật toán.

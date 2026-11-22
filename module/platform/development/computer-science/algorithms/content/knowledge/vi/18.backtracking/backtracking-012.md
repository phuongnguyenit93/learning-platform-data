# Ghi nhớ trạng thái thất bại và giới hạn sử dụng

## 1. Từ quay lui thuần túy đến ghi nhớ nhánh không có nghiệm

Trong **quay lui (backtracking)**, ta xây dựng một lời giải từng bước, thử các lựa chọn, đi sâu vào một nhánh và quay về thử nhánh khác. Cây tìm kiếm có thể rất lớn: với n phần tử được chọn/bỏ độc lập, có thể có tới 2^n lá.

Đôi khi **nhiều đường đi khác nhau** lại dẫn đến cùng một bài toán con. Nếu đã chứng minh từ một trạng thái nào đó **không thể hoàn tất thành nghiệm**, việc thử lại toàn bộ cây con tương đương là lãng phí. Ta có thể lưu trạng thái ấy vào một tập gọi là:

- **Failed-state memoization:** ghi nhớ trạng thái đã được chứng minh là thất bại.
- **Dead-state cache:** tập các trạng thái không có phần hoàn tất hợp lệ.
- **Negative caching:** lưu kết quả “không” để dùng lại; không nhất thiết lưu kết quả “có”.

Ví dụ bài **tổng tập con (subset sum)**: chọn một số phần tử của a sao cho tổng đúng bằng target, mỗi chỉ số được dùng tối đa một lần. Nếu đã xét i phần tử và còn thiếu r đơn vị tổng, trạng thái (i,r) hỏi:

> Có thể dùng một tập con của a[i],a[i+1],...,a[n-1] để tạo đúng tổng r không?

Nếu đã duyệt hết các nhánh từ (i,r) mà không thành công, lưu (i,r) là thất bại. Khi một đường quyết định khác gặp lại chính (i,r), ta có thể trả false ngay mà không tìm lại.

**Ý tưởng không phải “gặp một nút hai lần thì bỏ”.** Ta chỉ bỏ nhánh khi đã chứng minh **không có lời giải hợp lệ từ trạng thái ấy**, và khi khóa trạng thái mô tả đủ mọi yếu tố ảnh hưởng đến những lựa chọn sau này.

Trong chủ đề **Quay lui**, kỹ thuật này giữ nguyên cách thử/hoàn tác của DFS, nhưng sử dụng một bộ nhớ để tránh lặp lại những cây con đã biết vô ích. Khi các trạng thái trùng nhau nhiều và có thể biểu diễn gọn, sự kết hợp này tiến gần đến **quy hoạch động có ghi nhớ**; nếu trạng thái không tương đương hoặc việc khôi phục lời giải phụ thuộc đường đi, cache đơn giản có thể làm sai đáp án.

## 2. “Cùng trạng thái” phải có nghĩa là cùng bài toán còn lại

Điều kiện căn bản để dùng lại kết quả thất bại là **tính tương đương của hậu tố**:

> Hai tiền tố có thể dùng chung thông tin thất bại nếu, từ thời điểm hiện tại, chúng có **chính xác cùng tập lựa chọn tiếp theo và cùng điều kiện chấp nhận** cho phần còn lại.

Ta không cần hai đường đi giống nhau. Ta cần chứng minh rằng **mọi cách hoàn tất từ một đường đi cũng hợp lệ từ đường kia**, và ngược lại, ít nhất đối với câu hỏi tồn tại nghiệm đang giải.

### Khóa (index, remaining) trong tổng tập con

Giả sử mảng a **bất biến trong toàn bộ lần tìm kiếm**, các phần tử được dùng tối đa một lần và ta chỉ được chọn trong đoạn chỉ số i..n-1. Đặt:

~~~text
remaining = target - tong cac phan tu da chon

state = (index, remaining)

canFinish(index, remaining):
    co tap con nao cua cac index tu index den n-1
    co tong dung bang remaining khong?
~~~

Những gì đã chọn trước index không cần xuất hiện trong khóa, vì chúng chỉ ảnh hưởng đến bài toán tương lai qua **remaining**. Tất cả phần tử còn lại hoàn toàn giống nhau với cùng index. Ví dụ hai đường đi chọn các số 2 khác vị trí ở phần đầu có thể cùng dẫn đến (index=4,remaining=3). Từ đây, khả năng tạo tổng 3 bằng phần còn lại không phụ thuộc việc ta chọn số 2 ở vị trí nào trước đó.

Điều kiện này **không tự động đúng** nếu có các quy tắc khác như “không được chọn hai vị trí có cùng màu”, “các phần tử cùng nhóm phải đi cùng nhau” hoặc “không được chọn hai đỉnh kề nhau”. Khi đó, lịch sử chọn có thể ảnh hưởng trực tiếp đến tính hợp lệ của các lựa chọn tương lai; khóa (index,remaining) có thể thiếu thông tin.

### Một bảng kiểm trước khi chọn key

- Còn những **đối tượng nào** có thể chọn? Index, bitmask, tập đã dùng hay cấu trúc lưới?
- Có ràng buộc phụ thuộc **chữ số/ký tự/đỉnh ngay trước**, nhóm, màu, số lần sử dụng hoặc đường đi không?
- Cùng một key có luôn cho **cùng câu trả lời** ở mọi thời điểm của lần chạy không?
- Dữ liệu gốc có thay đổi trong lúc hoặc giữa những lần dùng cache không?
- Ta muốn biết **tồn tại một nghiệm**, **số nghiệm**, **tất cả nghiệm** hay **nghiệm tốt nhất**?

Chỉ khi các câu trả lời dẫn đến một trạng thái đủ thông tin mới được gộp các cây con dưới cùng một khóa. Cắt nhánh trên một khóa thiếu thông tin có thể **bỏ hẳn lời giải tồn tại**.

## 3. Vì sao có trạng thái lặp lại trong cây quay lui?

Xét a=[2,2,2,2,2,2], target=7, tất cả phần tử dương. Vì mọi số đều chẵn, **không có tập con nào** có tổng 7.

Trong cây lấy/bỏ, nhiều tiền tố khác nhau vẫn có cùng số phần tử đã xét và cùng tổng đã lấy. Chẳng hạn sau khi xét bốn phần tử đầu:

~~~text
Duong 1: lay index 0, bo 1,2,3 -> tong=2
Duong 2: bo 0, lay index 1, bo 2,3 -> tong=2
Duong 3: bo 0,1, lay index 2, bo 3 -> tong=2

Ca ba cung dan toi:
    index = 4
    remaining = 7 - 2 = 5
~~~

Tại (4,5), chỉ còn hai phần tử giá trị 2; không có cách nào tạo 5. Nếu DFS từ đường 1 đã xét cả nhánh lấy/bỏ của hai phần tử còn lại và kết luận false, hai đường sau không cần lặp lại phép tìm kiếm ấy.

Ta có thể xem cây chọn/bỏ được **gộp thành đồ thị trạng thái**:

~~~text
          (0,7)
          /   \
      lay 2    bo 2
       /          \
     (1,5)       (1,7)
        ...        ...
          \        /
             (4,5)    <- nhieu duong di chung state
               |
         da chung minh FALSE
               |
             DEAD
~~~

Hình là biểu diễn **khái niệm**, không khẳng định hai cạnh trực tiếp ở cùng mức từ (1,5) và (1,7) đều dẫn đến (4,5) trong một bước. Điều quan trọng là **nhiều chuỗi quyết định** có thể quy về một cặp (i,r). Nếu khóa đủ, kết quả của cây con ở đó được dùng chung.

### Không được đồng nhất hai đường đi khi xuất nghiệm

Hai tiền tố khác nhau có thể có **danh sách chỉ số đã chọn khác nhau** dù còn cùng (i,r). Nếu chỉ cần câu trả lời có tồn tại hay không, hai tiền tố ấy có tương lai Boolean giống nhau. Nếu cần **liệt kê các bộ chỉ số**, chúng có thể dẫn đến hai nghiệm khác nhau dù dùng chung cùng tập quyết định hậu tố. Khi ấy, việc đặt “đã thấy (i,r), bỏ qua toàn bộ lần thứ hai” không còn an toàn.

Ghi nhớ **thất bại thật sự** khác với đánh dấu **đã từng đi qua** một trạng thái; phần sau sẽ phân tích kỹ sự khác biệt này.

## 4. Quy trình DFS với tập trạng thái thất bại

Ta dùng một tập failed chứa **chỉ những trạng thái đã chứng minh không có hậu tố thành công**. Không lưu một trạng thái vào failed khi mới bước vào nút.

Mẫu thuật toán cho a[i]>0 và target≥0:

~~~text
dfs(i, remaining):
    if remaining == 0:
        return true     // Da tim duoc mot tap con dat tong.

    if i == n:
        return false    // Het phan tu ma chua du tong.

    state = (i, remaining)
    if state in failed:
        return false    // Da chung minh nhanh nay vo nghiem.

    if a[i] <= remaining:
        choose i
        if dfs(i+1, remaining-a[i]):
            undo or copy answer as required
            return true
        undo i

    if dfs(i+1, remaining):
        return true

    failed.add(state)  // CHI sau khi ca hai nhanh deu that bai.
    return false
~~~

**Thứ tự kiểm tra có ý nghĩa:**

1. remaining==0 là thành công của bài **tìm một nghiệm** với giá trị dương; ghi/chụp path nếu cần.
2. i==n mà remaining>0 là thất bại.
3. Kiểm tra failed chỉ sau khi các điều kiện đích/cơ sở đã rõ.
4. Thử lấy và bỏ; nếu một nhánh thành công, trả true mà **không** đánh dấu state thất bại.
5. Chỉ khi mọi lựa chọn đã xét đều false mới thêm state vào failed.

Với a[i]>0, nhánh lấy khi a[i]>remaining có thể bỏ qua: vì chỉ thêm số dương, tổng đã lấy không thể được giảm bởi phần còn lại. Nhưng **nhánh bỏ** vẫn phải xét nếu chưa chứng minh nó vô ích.

### Hoàn tác không được làm rò rỉ path

Nếu dùng ArrayList<Integer> path dùng chung giữa các lời gọi, vòng nhánh lấy phải có:

~~~text
path.add(i)
found = dfs(i+1, remaining-a[i])
path.remove(path.size()-1)

if found:
    return true
~~~

Khi gặp nghiệm, nên chụp path vào một danh sách bất biến **trước** khi trả true. Cách viết này giữ trạng thái path ở cha sạch ngay cả khi tìm được nghiệm. Nếu trả true thẳng trước khi remove, có thể vẫn dùng kết quả đúng trong một triển khai cụ thể, nhưng cấu trúc dùng chung sẽ còn các thay đổi chưa hoàn tác, dễ gây lỗi nếu mã được mở rộng.

**Không đánh dấu thất bại trên đường thành công:** từ một state có nghiệm, việc một nhánh thử trước bị sai **không** biến cả state thành thất bại. Chỉ được thêm vào failed sau khi **tất cả ứng viên hợp lệ** đã được thử và đều thất bại.

## 5. Ví dụ cầm tay: memo giúp tránh thử lại một cây con

Xét [2,2,2,2,2,2] và target=7. Nếu chọn **lấy trước, bỏ sau**:

- Lần gặp đầu ở (0,7), thử lấy 2, tới (1,5), tiếp tục cho tới những trạng thái ở sâu.
- Một state như (4,5) không thể hoàn tất vì chỉ có hai số 2 còn lại; sau khi xét hết nhánh, lưu failed.
- Khi một tiền tố khác dẫn tới (4,5), kiểm tra failed thành công và trả false ngay, không mở rộng các con dưới (4,5).
- Tất cả đường đi cuối cùng thất bại. Kết quả tìm một nghiệm là false, không có danh sách chỉ số.

Với a=[3,3,5,5], target=8, theo thứ tự **lấy trước, bỏ sau**:

1. Lấy index 0 (giá trị 3), remaining=5.
2. Thử lấy index 1 (3), remaining=2; các phần tử 5 còn lại quá lớn, nhánh thất bại.
3. Hoàn tác index 1, bỏ index 1, thử lấy index 2 (5), remaining=0.
4. Trả nghiệm [0,2], tổng 3+5=8.

Khi đã tìm một nghiệm, DFS dừng sớm. Tập failed có thể chỉ chứa một vài trạng thái thất bại đã duyệt trước đó; **không cần chứng minh mọi trạng thái còn lại**. Đó là lý do số state đã cache không thể hiện tổng số state có thể thất bại trên toàn không gian.

### Kết quả đếm thao tác của một cài đặt cụ thể

Với mã Java chạy độc lập ở phần 11, ta đếm một lần gọi dfs ngay khi vào hàm, một memo hit khi một cặp (index,remaining) đã thuộc failed, và một failed state khi thực sự thêm khóa mới vào tập.

| Đầu vào | Kết quả | Số lời gọi DFS | Memo hits | State thất bại được lưu |
| --- | --- | ---: | ---: | ---: |
| [3,3,5,5], target=8 | Nghiệm [0,2] | 7 | 0 | 2 |
| Sáu phần tử 2, target=7 | Không có nghiệm | 34 | 9 | 18 |
| [], target=0 | Nghiệm rỗng | 1 | 0 | 0 |

Các số đếm này phụ thuộc **chính thứ tự duyệt và vị trí đặt bộ đếm trong mã**, không phải tính chất toán học cố định của bài toán. Đổi từ lấy trước sang bỏ trước có thể làm số lời gọi và hit khác đi nhưng không đổi tính đúng.

## 6. Điều kiện an toàn để lưu một thất bại

Để failed.add(state) có giá trị logic, cần ba điều kiện đồng thời.

**A. Khóa chứa đủ thông tin ảnh hưởng đến tương lai.** Nếu hai nhánh có cùng key nhưng khác tập phần tử còn được phép dùng, khác điều kiện phụ, khác tiền tố cấm hoặc khác số lượt còn lại, ta không được suy từ thất bại của một nhánh sang nhánh kia.

**B. Trạng thái đã được giải trọn vẹn.** False phải có nghĩa “**mọi cách hoàn tất** đều thất bại”, không phải “ta vừa thử một ứng viên và ứng viên ấy sai”. Nếu dừng do giới hạn thời gian, bị ngắt, hết quota, hoặc một heuristic không bảo đảm, không thể tự coi đó là chứng minh vô nghiệm.

**C. Bài toán không đổi trong suốt thời gian dùng cache.** Dữ liệu a, target, ràng buộc hợp lệ và mục tiêu phải giống nhau giữa lúc cache và lúc tra. Nếu chúng thay đổi, cần xóa/phiên bản hóa cache, hoặc mở rộng key để biểu diễn thay đổi đó.

Có thể phát biểu bằng hàm:

~~~text
feasible(state, problemVersion) in {true, false}

failed co the ghi state neu:
    feasible(state, problemVersion) = false
    va ket qua do duoc chung minh tu toan bo cac nhanh hop le.
~~~

Nếu chỉ lưu cặp (i,r) mà gọi lại với **mảng a khác**, chẳng hạn a=[2,4] rồi a=[3,3], cùng (0,6) có thể có kết quả khác nhau; cache xuyên bài phải gắn với mảng, mục tiêu và các tham số liên quan, hoặc tạo một cache mới cho mỗi lần tìm kiếm.

### Vì sao chỉ dùng index là sai?

Với a=[3,5] và target=5:

- Trạng thái (index=1,remaining=5) có nghiệm bằng cách lấy a[1]=5.
- Trạng thái (index=1,remaining=2) thì không có nghiệm từ a[1]=5.

Nếu key chỉ là index=1, kết luận thất bại ở remaining=2 có thể làm ta bỏ nhầm state còn remaining=5. Tương tự, nếu key chỉ là remaining mà bỏ index, hai trạng thái có số phần tử còn lại khác nhau cũng có thể cho kết quả khác nhau.

**Nguyên tắc:** chỉ bỏ một thành phần của key khi đã chứng minh nó không ảnh hưởng đến tập hậu tố có thể chọn hoặc điều kiện đích.

## 7. Phản ví dụ quan trọng: cùng đỉnh nhưng tập visited khác nhau

Một lỗi khó nhận ra là lưu failed[vertex] trong bài tìm **đường đi đơn** (không được thăm lại đỉnh) với ràng buộc theo lịch sử. Tên đỉnh hiện tại thường **không đủ** để mô tả các đỉnh còn được dùng.

Xét đồ thị có hướng:

~~~text
S -> A
S -> B
A -> X
A -> T
B -> X
X -> A
~~~

Ta tìm một đường đi từ S đến T **phải đi qua X**, không được lặp đỉnh nào.

- Đường thử đầu **S → A → X** thất bại: từ X chỉ có cạnh đến A nhưng A đã được thăm; không được quay lại A. Nhánh A→T trước khi qua X cũng không đáp ứng điều kiện.
- Đường khác **S → B → X → A → T** là hợp lệ: ở lần tới X thứ hai, A **chưa** nằm trong visited, nên có thể đi tiếp qua A rồi tới T.

Cả hai nhánh đều từng ở vertex=X và đã đi qua X. Nếu sau nhánh đầu ta gán failed[X]=true rồi bỏ mọi lần đến X, ta sẽ **bỏ sót đường đi hợp lệ** của nhánh thứ hai.

**State đủ thông tin** ít nhất phải có vertex hiện tại, tập visited và những điều kiện đường đi còn lại (ở đây điều kiện đã đi qua X). Trên đồ thị nhỏ, visited có thể được mã hóa bằng bitmask, còn trên đồ thị lớn có thể dùng BitSet hoặc cấu trúc khác; số trạng thái (vertex,visited) trong trường hợp xấu có thể **tăng theo cấp số mũ**.

Điểm chính không phải lúc nào cũng phải lưu cả path bằng danh sách vào key. Ta có thể lưu **phần thông tin lịch sử thực sự ảnh hưởng đến hậu tố**. Với một bài tìm đường đi khác chỉ cần reachability trên đồ thị tĩnh và không có ràng buộc path-sensitive, có thể tồn tại thuật toán BFS/DFS với visited theo đỉnh hoàn toàn đúng; không được suy rằng ví dụ trên bác bỏ mọi cách dùng visited theo đỉnh.

## 8. Một ví dụ sai khác: đếm/liệt kê nghiệm mà bỏ mọi state đã gặp

Giả sử a=[1,1,1], target=2. Có ba tập con theo chỉ số:

~~~text
[0,1]
[0,2]
[1,2]
~~~

Hai đường tiền tố:

~~~text
Lay index 0, bo index 1 -> state (index=2,remaining=1)
Bo index 0, lay index 1 -> state (index=2,remaining=1)
~~~

đều có một cách hoàn tất từ suffix: lấy index 2. Nhưng hai kết quả cuối **[0,2] và [1,2]** khác nhau về bộ chỉ số.

Nếu dùng một Set visited để nói “(2,1) đã thấy rồi, bỏ lần thứ hai”, chương trình có thể chỉ sinh một trong hai nghiệm; kết quả **liệt kê hoặc đếm sẽ thiếu**.

### Ghi nhớ thất bại vẫn có thể hỗ trợ liệt kê

Nếu state thật sự có **0 cách hoàn tất** từ mọi đường đi tương đương, việc bỏ cây con ấy không làm mất nghiệm. Vì vậy, cache **chỉ các trạng thái chắc chắn thất bại** vẫn có thể là một pruning an toàn khi liệt kê, với điều kiện key đủ thông tin và không có nhánh nào bị kết luận false do dừng sớm.

Điều **không** an toàn là dùng một bộ seen chung để bỏ mọi state đã từng duyệt, bao gồm state có một hoặc nhiều cách hoàn tất, vì các tiền tố khác nhau cần tạo ra **những lời giải đầy đủ khác nhau**.

### Muốn đếm, hãy lưu số cách hoàn tất

Thay vì chỉ lưu Boolean failed, ta có thể định nghĩa:

~~~text
ways(i, remaining) =
    so bo chi so trong suffix a[i..n)
    co tong dung bang remaining

ways(i,r) =
    ways(i+1,r) +
    (r>=a[i] ? ways(i+1,r-a[i]) : 0)
~~~

Mỗi lần một tiền tố mới tới cùng (i,r), ta **cộng** số cách hậu tố vào kết quả của tiền tố ấy; không bỏ lần thứ hai như khi dùng visited. Đây là quy hoạch động đếm với **memoization lưu giá trị**, không chỉ negative caching.

Trường hợp a[i]=0 rất đáng chú ý: với a=[0,0,2], target=2, có **4** tập chỉ số hợp lệ vì mỗi phần tử 0 có thể được chọn hoặc bỏ độc lập. Nếu hàm đếm trả 1 ngay khi remaining==0 dù chưa xét hết phần tử, sẽ **đếm thiếu** những bộ có thêm số 0. Đối với mục tiêu đếm, base case an toàn là đã xét hết n phần tử thì trả 1 nếu remaining==0, ngược lại 0.

Ví dụ Java ở phần 11 triển khai cả **tìm một nghiệm bằng failed states** và **đếm nghiệm bằng memo lưu BigInteger**, để không lẫn hai kiểu kết quả.

## 9. Các giới hạn khác khi áp dụng ghi nhớ thất bại

### 9.1 Ràng buộc phụ thuộc vào đường đi

Các bài hoán vị có cấm hai giá trị kề nhau, đường đi không lặp đỉnh, N quân hậu với cờ cột/đường chéo, Sudoku với các giá trị đã điền, xếp lịch có tài nguyên đã dùng... thường cần **nhiều hơn một chỉ số độ sâu** để mô tả tương lai.

Ví dụ trong N quân hậu, lưu failed[row] là sai: cùng hàng row nhưng các cột và đường chéo đã bị chiếm khác nhau sẽ làm số cột hợp lệ ở hàng sau khác nhau. Khóa đúng cần bao gồm những tập cột/đường chéo ảnh hưởng phần còn lại, chẳng hạn các bitmask đã dùng khi n nhỏ.

Khi key phải chứa toàn bộ lịch sử, số trạng thái có thể gần bằng số nút đã thử; chi phí hash, lưu trữ và so sánh key khi ấy có thể lớn hơn lợi ích tránh tính lặp.

### 9.2 Cắt nhánh bằng nghiệm tốt nhất chưa chắc là “vô nghiệm”

Trong branch-and-bound cho tối ưu hóa, một nhánh có thể bị cắt vì **không thể cải thiện nghiệm tốt nhất hiện có**. Điều này khác với việc nhánh ấy **không chứa nghiệm hợp lệ nào**.

Nếu lưu cờ failed cho một state chỉ vì nó không tốt hơn best ở hoàn cảnh hiện tại, rồi dùng cờ ấy trong bài **tìm bất kỳ nghiệm** hoặc **liệt kê mọi nghiệm**, kết luận sẽ sai. Ngay cả khi chỉ tối ưu, cận còn phụ thuộc chi phí đã tích lũy, best, điều kiện phụ và quy tắc xử lý nghiệm đồng tối ưu. Cần định nghĩa rõ loại kết quả đang cache: “không có nghiệm”, “không có nghiệm đạt ngưỡng”, hay “giá trị tối ưu của hậu tố”.

Nếu tối ưu đường đi, hai lần tới cùng đỉnh với **chi phí tích lũy khác nhau** có thể yêu cầu phép so sánh dominance, chứ không thể đơn giản gán failed[vertex] sau lần đầu.

### 9.3 Dữ liệu và ràng buộc bị sửa

Một state có thể vô nghiệm trước khi cập nhật nhưng có nghiệm sau khi thêm vật phẩm, sửa trọng số, bỏ ràng buộc hoặc đổi target. Cache không tự nhận ra thay đổi.

Các cách an toàn:

- Tạo cache mới cho **mỗi** lần gọi trên một dữ liệu bất biến.
- Gắn mã phiên bản dữ liệu vào key hoặc cache namespace.
- Xóa các entry liên quan khi có cập nhật, nếu chứng minh được phạm vi ảnh hưởng.

Một Map nằm trong singleton mà dùng chung cho nhiều bài toán khác nhau **không an toàn** nếu khóa không mang theo ngữ cảnh bài.

### 9.4 Đường tìm kiếm có chu trình

Trong tìm kiếm trên đồ thị có chu trình, một state có thể được gặp lại khi **lời gọi đầu tiên chưa hoàn tất**. Không được đánh dấu nó là thất bại chỉ vì đang “in progress”. Nếu nhầm “đang xét” thành “đã chứng minh false”, có thể bỏ nhầm đường đi hợp lệ.

Với đồ thị có chu trình, cần chọn thuật toán phù hợp: visited trên đồ thị cho bài reachability thông thường; DFS với trạng thái visiting/finished và quy tắc xử lý chu trình; DP trên DAG; hoặc các thuật toán đồ thị khác. Nếu số đường đi có thể vô hạn vì chu trình và được phép đi lặp, phải định nghĩa bài toán đếm rõ trước khi memoize.

### 9.5 Heuristic, timeout và trạng thái không rõ

Một nhánh chưa được khám phá hết do hết thời gian không phải bằng chứng thất bại. Tốt hơn nên có ba kết quả logic **TRUE, FALSE, UNKNOWN** khi giới hạn tài nguyên có thể ngắt quá trình tìm kiếm; chỉ lưu FALSE khi đã kiểm tra đủ và có chứng minh. Nếu dùng trạng thái “chưa xét” và “đang xét”, không được coi cả hai như FALSE.

### 9.6 Không có trạng thái lặp lại

Nếu mỗi đường quyết định có một state độc nhất, cache chỉ làm tăng thời gian tra cứu và dùng bộ nhớ nhưng không tạo memo hit. Trong một cây hoán vị mà key chứa chính xác toàn bộ chuỗi thứ tự đã chọn, hai đường khác nhau không gặp cùng key; lúc đó memoization hầu như không có tác dụng.

Kỹ thuật chỉ hiệu quả khi có **trạng thái tương đương xuất hiện nhiều lần**, đặc biệt khi cây con sau chúng đủ đắt để chi phí tra cứu nhỏ hơn chi phí tính lại.

## 10. Thiết kế cache key, vòng đời và chính sách ghi

### Dùng record hoặc đối tượng bất biến làm key

Trong Java, record phù hợp với state nhỏ:

~~~java
record State(int index, int remaining) {}
~~~

Một record như vậy có equals/hashCode theo trường; HashSet<State> có thể tra cứu theo giá trị nội dung thay vì định danh đối tượng. Điều kiện là trạng thái thực sự chỉ phụ thuộc vào index và remaining.

**Tránh dùng mảng mutable trực tiếp làm key:** int[] dùng equals/hashCode theo định danh chứ không so các phần tử, và sửa một khóa mutable sau khi đưa vào HashMap có thể làm các lần tìm sau sai (với kiểu có hash phụ thuộc nội dung). Nếu state cần bitmask lớn, có thể dùng bản sao BitSet với chiến lược bất biến rõ ràng hoặc một lớp key bất biến.

### Khi nào thêm một failed state?

Chỉ sau khi:

1. Kiểm tra base case chưa đạt.
2. Xét mọi ứng viên hợp lệ hoặc có một chứng minh cắt nhánh đủ mạnh.
3. Tất cả cách hoàn tất đều không thành công.
4. Khóa đã được tạo từ trạng thái **trước khi thao tác chọn tiếp**, không lấy từ các mảng cờ đã bị thay đổi tạm ở nhánh con.

Không cần thêm trạng thái **cơ sở chắc chắn thất bại** nếu chúng không lặp đủ nhiều để đáng lưu; đây là lựa chọn tối ưu hiệu năng, không thay đổi tính đúng. Trong ví dụ Java, state ở index==n trả false trực tiếp.

### Giới hạn cache và chính sách loại bỏ

Với một bài tồn tại nghiệm mà cache chỉ lưu false, xóa một phần entry khỏi cache **không làm câu trả lời sai**: lần gặp lại state chỉ phải tính lại từ đầu. Do đó có thể đặt hạn mức số entry hoặc cơ chế eviction để tiết kiệm RAM, miễn là các entry còn lại đúng với dữ liệu hiện hành.

Nhưng các entry **sai** (do key thiếu hoặc stale data) không được sửa bằng việc tăng kích thước cache. Kích thước cache lớn chỉ tăng khả năng các kết luận sai được tái sử dụng.

Nếu giới hạn bộ nhớ, có thể quyết định chỉ cache state ở độ sâu nào đó, state có nhiều nhánh hoặc state được gặp nhiều lần; cần đo hiệu quả thực tế trên tải bài toán.

## 11. Java 17 – tìm một nghiệm và đếm nghiệm bằng hai loại memo khác nhau

Chương trình sau minh họa hai API với hợp đồng rõ ràng:

1. **findOneSubset** chỉ nhận số nguyên dương và target≥0, trả có/không và **một bộ chỉ số** đạt tổng đích. Nó dùng HashSet<State> lưu **chỉ các trạng thái thất bại**.
2. **countSubsets** nhận số nguyên **không âm** (bao gồm 0), dùng HashMap<State,BigInteger> lưu **số cách hoàn tất**, trả số tập chỉ số khác nhau có tổng đúng target.

Việc cho phép 0 trong countSubsets là có chủ đích để chỉ ra vì sao base case của **đếm** khác với **tìm một nghiệm**. Cả hai hàm đều xét mỗi phần tử tối đa một lần, và dùng chỉ số gốc của mảng đầu vào.

Lưu toàn bộ mã vào tệp **FailedStateMemoDemo.java**:

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class FailedStateMemoDemo {

    record State(int index, int remaining) {}

    record SearchResult(boolean found, List<Integer> indices,
                        long calls, long memoHits, int failedStates) {}

    private static final class Search {
        final int[] a;
        final Set<State> failed = new HashSet<>();
        final List<Integer> path = new ArrayList<>();
        List<Integer> answer = List.of();
        long calls;
        long memoHits;

        Search(int[] input) {
            this.a = input.clone();
        }

        boolean dfs(int index, int remaining) {
            calls++;

            if (remaining == 0) {
                answer = List.copyOf(path);
                return true;
            }
            if (index == a.length) {
                return false;
            }

            State state = new State(index, remaining);
            if (failed.contains(state)) {
                memoHits++;
                return false;
            }

            // Nhanh lay: chi thu neu khong vuot target con thieu.
            if (a[index] <= remaining) {
                path.add(index);
                boolean found = dfs(index + 1, remaining - a[index]);
                path.remove(path.size() - 1); // Undo ca khi tim thay.

                if (found) {
                    return true;
                }
            }

            // Nhanh bo: khong thay doi path.
            if (dfs(index + 1, remaining)) {
                return true;
            }

            // Tat ca nhanh deu FALSE: day moi la DEAD state.
            failed.add(state);
            return false;
        }
    }

    // Tim MOT nghiem, moi gia tri bat buoc duong.
    static SearchResult findOneSubset(int[] values, int target) {
        Objects.requireNonNull(values, "values");
        if (target < 0) {
            throw new IllegalArgumentException(
                    "target must be nonnegative");
        }
        for (int value : values) {
            if (value <= 0) {
                throw new IllegalArgumentException(
                        "all values must be positive");
            }
        }

        Search search = new Search(values);
        boolean found = search.dfs(0, target);
        return new SearchResult(
                found,
                search.answer,
                search.calls,
                search.memoHits,
                search.failed.size());
    }

    // Dem tat ca TAP CHI SO, cho phep so 0, tra BigInteger.
    static BigInteger countSubsets(int[] values, int target) {
        Objects.requireNonNull(values, "values");
        if (target < 0) {
            throw new IllegalArgumentException(
                    "target must be nonnegative");
        }
        for (int x : values) {
            if (x < 0) {
                throw new IllegalArgumentException(
                        "all values must be nonnegative");
            }
        }

        return countDfs(
                values, 0, target, new HashMap<State, BigInteger>());
    }

    private static BigInteger countDfs(
            int[] values, int index, int remaining,
            Map<State, BigInteger> memo) {

        // CHI khi da quyet dinh het, mot tap chi so moi day du.
        if (index == values.length) {
            return remaining == 0
                    ? BigInteger.ONE : BigInteger.ZERO;
        }

        State state = new State(index, remaining);
        BigInteger cached = memo.get(state);
        if (cached != null) {
            return cached;
        }

        // Bo gia tri hien tai.
        BigInteger ways = countDfs(
                values, index + 1, remaining, memo);

        // Lay gia tri hien tai; voi x=0, nhanh van la
        // mot bo chi so KHAC nhanh bo.
        if (values[index] <= remaining) {
            ways = ways.add(countDfs(
                    values, index + 1,
                    remaining - values[index], memo));
        }

        memo.put(state, ways);
        return ways;
    }

    public static void main(String[] args) {
        SearchResult ok = findOneSubset(
                new int[]{3, 3, 5, 5}, 8);
        System.out.println("found = " + ok.found()
                + ", indices = " + ok.indices());
        System.out.println("success stats: calls=" + ok.calls()
                + ", hits=" + ok.memoHits()
                + ", failed=" + ok.failedStates());

        SearchResult no = findOneSubset(
                new int[]{2, 2, 2, 2, 2, 2}, 7);
        System.out.println("impossible = " + no.found());
        System.out.println("failure stats: calls=" + no.calls()
                + ", hits=" + no.memoHits()
                + ", failed=" + no.failedStates());

        SearchResult empty = findOneSubset(new int[0], 0);
        System.out.println("empty target: found=" + empty.found()
                + ", indices=" + empty.indices());

        System.out.println("count three ones = " +
                countSubsets(new int[]{1, 1, 1}, 2));
        System.out.println("count two zeros = " +
                countSubsets(new int[]{0, 0, 2}, 2));

        try {
            findOneSubset(new int[]{2, 0}, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid search: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac FailedStateMemoDemo.java
java FailedStateMemoDemo
~~~

**Stdout chính xác** với thứ tự nhánh lấy trước, bỏ sau và vị trí đếm của mã:

~~~text
found = true, indices = [0, 2]
success stats: calls=7, hits=0, failed=2
impossible = false
failure stats: calls=34, hits=9, failed=18
empty target: found=true, indices=[]
count three ones = 3
count two zeros = 4
invalid search: all values must be positive
~~~

### Phân tích phương thức findOneSubset

- Hàm nhận int[] và target; từ chối mảng null, target âm, giá trị bằng 0 hoặc âm. Đây là hợp đồng **tìm một nghiệm với số dương**; không cố xử lý mọi biến thể trong cùng một hàm.
- Search sao chép mảng dữ liệu để state của một lần tìm không bị phụ thuộc vào việc người gọi sửa mảng sau khi bắt đầu. Cache là thuộc tính của **đúng một đối tượng Search** nên không rò rỉ từ một lần gọi sang lần khác.
- Mỗi lời gọi dfs tăng calls; nếu remaining==0, chụp List.copyOf(path) và trả true.
- Tại state chưa thành công, kiểm tra failed trước khi thử các nhánh. Nếu có trong cache, tăng memoHits rồi false.
- Nhánh lấy thêm index vào path và **remove ngay sau khi con trả về**, kể cả con trả true. Khi thành công, bản chụp answer đã độc lập với path đang được hoàn tác.
- Chỉ sau khi nhánh lấy (nếu hợp lệ) và nhánh bỏ đều false, state mới được thêm vào failed.

Với target=7 và sáu số 2, mọi tổng tập con là số chẵn nên không có nghiệm. Bộ đếm memoHits=9 chứng tỏ một số state đã được dùng lại; calls vẫn tính các lần gọi tới state cached, nhưng những lần ấy không mở rộng cây con.

### Phân tích phương thức countSubsets

- Đếm theo **tập chỉ số**: chọn hoặc bỏ hai số 1 ở hai vị trí khác nhau là hai quyết định khác nhau, dù giá trị giống nhau.
- Với a=[1,1,1], target=2, có ba bộ chỉ số (0,1), (0,2), (1,2), nên trả 3.
- Với a=[0,0,2], target=2, chỉ số của số 2 phải được chọn, còn mỗi số 0 có hai lựa chọn độc lập; tổng 2×2=4 cách.
- countDfs chỉ chốt kết quả khi index==n, vì dừng ở remaining==0 trước đó sẽ mất các cách còn chọn thêm 0.
- HashMap lưu **số cách** kể cả BigInteger.ZERO, nên cùng một hậu tố được tính một lần và số cách có thể được cộng cho nhiều tiền tố khác nhau mà **không làm mất nghiệm**.
- BigInteger tránh tràn số cách khi n lớn. Chương trình vẫn có độ sâu đệ quy O(n); nếu n cực lớn có thể cần thuật toán lặp.

### Vì sao không dùng chung một kiểu cache?

HashSet<State> lưu “đã chứng minh vô nghiệm” là đủ để **tìm một nghiệm** và quay lui dừng sớm. HashMap<State,BigInteger> trả **số cách hoàn tất** là cần thiết để **đếm tất cả**. Thay mọi lần gặp key trùng bằng việc bỏ qua sẽ sai trong bài đếm.

**Một state có thể tồn tại nhiều lời giải:** nếu cache chứa true nhưng chỉ cần tìm một bộ chỉ số, còn cần lưu quyết định hoặc tái dựng đường đi. Nếu cache chứa một bộ chỉ số hoàn tất từ suffix thì cũng phải nối đúng với prefix hiện tại. Chỉ cache false đơn giản hơn, vì false không đòi khôi phục witness.

## 12. Phân tích độ phức tạp và hiệu quả thực tế

Với bài subset sum a[i]>0, target nguyên không âm T, mỗi state hợp lệ có dạng (i,r) với 0≤i≤n, 0≤r≤T. Do đó **số state phân biệt tối đa O(nT)**. Khi dùng một bảng đã chứng minh thất bại và mỗi state không thành công chỉ mở rộng một lần, ta có:

| Hạng mục | Không ghi nhớ | Ghi nhớ failed states đầy đủ |
| --- | --- | --- |
| Số đường quyết định tiềm năng | Tối đa 2^n lá | Tối đa O(nT) state phân biệt được xử lý đầy đủ |
| Thời gian tìm kiếm trường hợp xấu | O(2^n) nút, chưa kể sao chép kết quả | O(nT) kỳ vọng với hash O(1), dưới giả thiết state/key của bài |
| Bộ nhớ phụ ngoài đầu ra | O(n) stack + path | O(n) stack/path + O(nT) cache |
| Khôi phục một nghiệm | Có thể giữ path | Có thể giữ path; cache false không phải nghiệm |
| Lợi thế thực tế | Không có overhead hash | Giảm thử lại khi nhiều đường dẫn trùng state |

**O(nT) là giả đa thức:** T là giá trị số target, không phải số bit để biểu diễn nó. Nếu target rất lớn, số state có thể khổng lồ; một HashSet không tự biến bài toán tổ hợp thành dễ trong mọi trường hợp. Chi phí hashing, allocation, garbage collection và kích thước mỗi record cũng có thể lớn so với mảng boolean/bitset.

Trong ví dụ Java, a là int và target int, nên remaining nằm trong [0,T]. Độ sâu DFS O(n), bộ nhớ path O(n). Các nhánh dư có thể bị cắt sớm khi một phần tử lớn hơn remaining. Số lời gọi vẫn có thể nhỏ hơn O(nT) rất nhiều nếu gặp nghiệm nhanh.

**Khi chỉ cần câu trả lời tồn tại**, quy hoạch động bottom-up với boolean[T+1] và vòng tổng giảm có thể dùng O(T) bộ nhớ và O(nT) thời gian, thường ít overhead hơn HashSet<State>. Nhưng DFS có failed cache có thể thắng trong một số bài khi chỉ thăm một phần rất nhỏ không gian state hoặc gặp nghiệm sớm.

### Khi nào memo không đáng giá?

- n nhỏ, không gian thử đã rất ít.
- Nhánh hầu như không lặp trạng thái, hoặc key phải mang cả path dài.
- Các ràng buộc quá động, cache thường phải xóa.
- Phép xử lý một state rất rẻ nhưng tạo key/hashing rất đắt.
- Bộ nhớ bị giới hạn chặt và số state thất bại tăng nhanh.
- Mục tiêu là **in mọi lời giải** và hầu hết các nhánh đều chứa nghiệm; failed cache sẽ ít hit.

Có thể đo **số lời gọi, số memo hit, số failed states được lưu, thời gian chạy và bộ nhớ** trên dữ liệu thực. Một tỷ lệ hit cao chưa đủ để chứng minh tổng thời gian thấp nếu bản thân HashMap/HashSet có chi phí lớn.

## 13. Chứng minh tính đúng của cache thất bại

Ta xét bài tìm một tập con đạt target với a[i]>0 và target≥0. Mệnh đề cần chứng minh:

> Với mọi (i,r), dfs(i,r) trả true nếu và chỉ nếu có tập con của các phần tử từ i đến n-1 có tổng r; nếu (i,r) được thêm vào failed thì không có tập con như vậy.

**Cơ sở:**

- Nếu r=0, tập con rỗng của suffix tạo đúng 0; dfs trả true. Trong bài tìm **một** nghiệm với mọi a[i]>0, không cần tiếp tục chọn phần tử nào.
- Nếu i=n và r>0, không còn phần tử nào để tạo tổng dương; dfs trả false.

**Bước quy nạp:** giả sử kết quả đúng với các trạng thái ở i+1. Với phần tử a[i], một tập con của suffix từ i hoặc:

1. **Có lấy i:** chỉ có thể đạt r nếu a[i]≤r, khi đó các phần tử sau phải tạo r-a[i].
2. **Không lấy i:** các phần tử sau phải tạo r.

Hai trường hợp bao phủ mọi tập con suffix hợp lệ. DFS thử cả hai trường hợp có thể, trừ khi đã có một nhánh trả true. Vì vậy DFS trả true khi có ít nhất một tập con đạt r; nếu cả hai trả false, không có tập con nào. Khi đó việc lưu failed.add(i,r) là chính xác.

**Tính đúng của memo hit:** khóa (i,r) cùng với mảng a bất biến xác định cùng bài toán suffix; do failed chỉ chứa những trạng thái đã được chứng minh false, mọi lần tra lại key ấy đều có thể trả false mà không đổi kết quả. Điều này đúng dù tiền tố path trước i khác nhau, vì tương lai không bị ảnh hưởng bởi path ngoài phần tổng đã được biểu diễn trong r.

**Tính đúng của path:** mỗi lần nhánh lấy thêm một index i rồi chuyển sang i+1; do đó các chỉ số luôn tăng và không thể trùng. remaining giảm đúng a[i]. Khi remaining về 0, tổng các giá trị đã chọn đúng target; List.copyOf(path) chụp nghiệm trước hoàn tác, nên lời giải trả về là một witness hợp lệ.

Chứng minh trên **không** còn áp dụng nguyên xi khi phần tử âm, khi có ràng buộc theo visited, khi phải dùng đúng k phần tử hoặc khi mục tiêu là mọi nghiệm mà điều kiện dừng/đếm khác đi. Các trường hợp ấy cần bổ sung state và chứng minh mới.

## 14. Kiểm thử theo thuộc tính và đối chứng brute force

Một thuật toán backtracking có cache dễ sai âm thầm: trả false trên cả những trường hợp thật sự có nghiệm. Vì vậy bộ kiểm thử cần đối chiếu kết quả với một cách giải đơn giản nhưng độc lập trên các bộ dữ liệu nhỏ.

### Với findOneSubset

- Nếu found=true, indices là danh sách chỉ số hợp lệ, tăng nghiêm ngặt, không trùng và tổng các a[index] đúng bằng target.
- Nếu found=false và n≤20, brute force trên 2^n tập con xác nhận không có bộ nào đạt target.
- Với target=0 và mọi giá trị dương, phải trả found=true, indices=[].
- Với mảng rỗng, target>0, trả found=false.
- Hai giá trị bằng nhau ở hai vị trí khác nhau vẫn là hai đối tượng khác nhau.
- Một lần gọi trên a khác không được chịu ảnh hưởng của cache từ lần gọi trước.
- Mỗi state trong failed phải có lời giải suffix bằng 0 cách; có thể xác minh bằng brute force hậu tố trên n nhỏ.
- Bật hoặc tắt cache phải trả **cùng found**, mặc dù số calls có thể khác.
- Kết quả của SearchResult không phụ thuộc vào những thay đổi về sau ở mảng input hoặc path nội bộ.

### Với countSubsets

- Với n≤20, đếm tất cả bitmask có tổng target và so kết quả BigInteger.
- count([1,1,1],2)=3; không gộp các phần tử trùng giá trị.
- count([0,0,2],2)=4; mỗi số 0 nhân đôi số cách.
- count([0,0],0)=4, không dừng sớm khi remaining=0.
- count([],0)=1, vì có đúng một tập chỉ số rỗng.
- count([],1)=0.
- Với a[i]≥0, số cách không âm và không vượt 2^n.
- Bảng memo có thể chứa BigInteger.ZERO để ghi nhớ trạng thái không có cách; 0 **không** được coi là “chưa tính”.

### Kiểm chứng phản ví dụ path-sensitive

Viết kiểm thử cho đồ thị S,A,B,X,T ở phần 7:

- Đường S→A→X phải thất bại trong mô hình đường đi đơn có yêu cầu qua X.
- Đường S→B→X→A→T phải thành công.
- Một cache chỉ theo vertex=X có thể bỏ đường hợp lệ và phải bị kiểm thử bác bỏ.
- Cache theo trạng thái đủ thông tin (vertex,visited,đã qua X) không được bác bỏ đường hợp lệ ấy.

### Các ca thử ngắn

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| [3,3,5,5], target=8 | found=true, chỉ số [0,2] theo lấy trước |
| Sáu số 2, target=7 | found=false, cache có memo hits |
| [], target=0 | found=true, indices=[] |
| [], target=1 | found=false |
| [4], target=4 | found=true, indices=[0] |
| [1,1,1], target=2 (đếm) | BigInteger 3 |
| [0,0,2], target=2 (đếm) | BigInteger 4 |
| [0,0], target=0 (đếm) | BigInteger 4 |
| [2,0], target=2 trong findOneSubset | Từ chối vì giá trị không dương |
| [-1,2], target=1 trong countSubsets | Từ chối vì giá trị âm |
| target âm | Từ chối theo hợp đồng |
| Cùng state nhưng dữ liệu a khác | Không tái sử dụng cache cũ |

**Đối chứng brute force:** với n nhỏ, một bitmask đại diện một tập chỉ số. Duyệt mask từ 0 tới 2^n-1, cộng các a[i] có bit i=1 và so với target. Để kiểm tra tìm một nghiệm, chỉ cần xác minh tồn tại ít nhất một mask; để kiểm tra đếm, cộng mọi mask phù hợp. Đây là oracle độc lập với thứ tự đệ quy và cơ chế memo.

## 15. Các lỗi phổ biến

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Đánh dấu failed ngay khi vào state | Bỏ cây con chưa được xét hết | Chỉ lưu sau khi mọi nhánh thất bại |
| Cache false sau khi một ứng viên sai | Bỏ những ứng viên khác có nghiệm | Duyệt đủ các lựa chọn hợp lệ |
| Key chỉ có index, bỏ remaining | Gộp các bài toán suffix khác tổng | Dùng state đủ như (index,remaining) |
| Key chỉ có đỉnh, bỏ visited | Sai bài đường đi đơn/path-sensitive | Gắn tập visited hoặc cấu trúc tương đương |
| Dùng cache giữa các dữ liệu đã thay đổi | Tái dùng kết luận không còn đúng | Reset/phiên bản hóa cache |
| Đồng nhất “đã thăm” với “thất bại” | Bỏ nghiệm khi state có cách hoàn tất | Chỉ cache dead thật sự, không phải seen |
| Dùng visited-state pruning khi liệt kê | Mất các nghiệm có prefix khác nhau | Chỉ prune state có 0 cách; hoặc lưu số cách |
| Tính đếm bằng boolean false/true | Không phân biệt 1 và nhiều cách | Memo BigInteger số cách |
| Dừng đếm tại remaining=0 dù còn số 0 | Đếm thiếu các tổ hợp chứa 0 | Với đếm, xử lý tới i=n |
| Dùng kết luận “không cải thiện best” như vô nghiệm | Sai mục tiêu tìm/đếm khác | Phân biệt infeasible với non-improving |
| Bị timeout nhưng lưu failed | Kết luận false không được chứng minh | Phân biệt FALSE và UNKNOWN |
| Quên undo path hoặc cờ used | Nhánh kế tiếp bị nhiễm state | Hoàn tác đủ thay đổi |
| Lưu tham chiếu ArrayList khi gặp nghiệm | Kết quả bị sửa sau khi quay lui | Dùng List.copyOf(path) |
| Key mutable không có equality ổn định | HashSet/HashMap tra sai | Dùng record hoặc key bất biến |
| Không đo chi phí cache | Dùng RAM nhiều hơn nhưng không nhanh | Đo hit rate, calls, memory và runtime |
| Cache chỉ có kết quả true mà không có lựa chọn | Khó dựng một witness | Lưu parent/decision hoặc tái dựng |
| Dùng memo trên chu trình như DAG | Sai khi state đang xử lý | Phân biệt in-progress/completed, xử lý chu trình |
| Tin rằng memo luôn đa thức | Bỏ qua số trạng thái có thể hàm mũ | Phân tích state space và key size |

**Thử nghiệm đặc biệt hữu ích:** một phiên bản code cố ý thêm state vào failed **ngay trước khi thử nhánh lấy** có thể vẫn đúng ở vài dữ liệu nhỏ nhưng sẽ sai khi gặp cùng state trong lúc chưa duyệt xong. Không coi “chạy đúng một ví dụ” là chứng minh cache đúng.

## 16. Bài tập tự luyện

1. Vẽ cây lấy/bỏ cho a=[2,2,2,2], target=5. Ghi rõ mọi cặp (index,remaining) xuất hiện lặp và trạng thái nào có thể lưu failed sau khi xét xong nhánh.
2. Dùng a=[3,3,5,5], target=8, mô phỏng thứ tự **lấy trước, bỏ sau**, ghi từng lần path.add, path.remove và thời điểm cache một state thất bại; giải thích vì sao nghiệm là [0,2].
3. Viết phiên bản DFS **không có memo**, đối chiếu found và số calls với phiên bản có failed HashSet trên các đầu vào tất cả số chẵn, target lẻ.
4. Đổi hàm findOneSubset sang cho phép giá trị 0 nhưng chỉ cần **một** nghiệm. Có cần thay base case remaining==0 không? Vì sao điều đó khác hàm **đếm mọi bộ chỉ số**?
5. Cho a=[1,1,1], target=2, chứng minh hai prefix khác nhau có thể đến (index=2,remaining=1). Vì sao một Set visited sẽ đếm thiếu, trong khi HashMap<State,BigInteger> vẫn đếm được 3?
6. Chuyển từ tìm một nghiệm sang **liệt kê tất cả bộ chỉ số** với target. Hãy nêu thời điểm an toàn để prune bằng failed-only và lý do không được bỏ state thành công đã gặp trước.
7. Vẽ đồ thị S,A,B,X,T ở phần 7, liệt kê tập visited khi tới X từ hai tiền tố. Chỉ ra khóa state còn thiếu thành phần gì nếu chỉ dùng vertex.
8. Một bài N quân hậu có state row=4 ở hai nhánh khác nhau. Hãy thiết kế cache key đủ để phản ánh cột và đường chéo đã dùng; đánh giá số state tiềm năng và liệu cache có đáng giá không.
9. Trong branch-and-bound tối ưu, phân biệt ba thông điệp “không có nghiệm”, “có nghiệm nhưng không tốt hơn best” và “chưa biết vì timeout”. Những thông điệp nào có thể được lưu vào cùng một Set failed?
10. Viết kiểm thử property-based sinh mảng dương độ dài tối đa 16, target ngẫu nhiên; so found của memo DFS với brute force 2^n và kiểm tra mọi indices được trả.
11. Mở rộng countSubsets thành đếm modulo M dương. Bảo đảm cách cộng không tràn kiểu trung gian và không xem giá trị phần dư 0 như “chưa memo”.
12. Thử thay HashSet<State> bằng bảng boolean failed[index][remaining] cho target nhỏ. So sánh bộ nhớ thực tế, chi phí tra cứu và nguy cơ cấp phát quá lớn khi target tăng.
13. Giả sử mảng a thay đổi giữa hai truy vấn nhưng bạn muốn tái sử dụng một bộ nhớ. Hãy nêu cách mã hóa version vào key hoặc xóa cache, và tạo kiểm thử phát hiện stale result.
14. Với một bài đường đi có chu trình, giải thích vì sao “đang xử lý” không đồng nghĩa “đã chứng minh false”. Đề xuất ba trạng thái UNVISITED, IN_PROGRESS, FINISHED khi cần.
15. Phân tích trường hợp toàn các giá trị khác biệt rất lớn khiến hiếm khi có cùng (index,remaining). Khi nào HashSet thất bại tiêu tốn nhiều hơn việc tính lại?
16. Cho một bài toán chỉ yêu cầu **một** nghiệm và một bài cần **mọi** nghiệm, trình bày khác biệt về điều kiện dừng, cách cache, chi phí đầu ra và cách kiểm thử tính đầy đủ.

**Kết luận:** ghi nhớ trạng thái thất bại chỉ đúng khi **(1) state mô tả đủ mọi ảnh hưởng lên các bước tiếp theo, (2) toàn bộ lựa chọn từ state đã được giải để chứng minh không có nghiệm, và (3) dữ liệu cùng mục tiêu không thay đổi trong vòng đời cache**. Trong backtracking, cách này có thể tránh thử lại nhiều cây con, nhưng không nên biến nó thành một tập “visited” dùng cho mọi mục đích. Với bài cần đếm, liệt kê, đường đi phụ thuộc visited hoặc tối ưu có cận động, phải thiết kế trạng thái và loại thông tin memo phù hợp, nếu không chương trình có thể chạy nhanh hơn chỉ vì đã **bỏ sót lời giải**.

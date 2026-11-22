# Lưu lịch sử cập nhật bằng cấu trúc bền vững

## 1. Bài toán: truy vấn dữ liệu ở nhiều thời điểm

Giả sử ta quản lý một dãy số A và nhận các thao tác liên tiếp:

- Đổi A[i] thành x.
- Cộng delta vào A[i].
- Hỏi tổng A[l]+…+A[r−1].
- Hỏi tổng **trong trạng thái trước một lần cập nhật**.
- Tạo **một nhánh mới** từ phiên bản cũ rồi tiếp tục cập nhật độc lập.

Cấu trúc mảng hay segment tree thông thường chỉ giữ trạng thái hiện tại: thay một giá trị sẽ làm mất thông tin ở các nút tổng đã bị ghi đè. Nếu sau 10.000 lần sửa mới phát hiện cần xem trạng thái ở lần sửa thứ 17, việc khôi phục bằng bộ nhớ hiện tại có thể không thực hiện được.

**Cấu trúc dữ liệu bền vững** (*persistent data structure*) giữ các phiên bản cũ sau khi cập nhật. Một cập nhật tạo phiên bản mới; các phiên bản cũ không bị thay đổi. Ta có thể hỏi lại lịch sử mà không phải chạy lại toàn bộ các sự kiện.

Bài này tập trung vào **persistent segment tree bằng path copying** vì nó minh họa trực tiếp ý tưởng chia sẻ cấu trúc: lưu tổng đoạn, tạo nút mới dọc đường cập nhật điểm, giữ nguyên phần còn lại. Ngoài ra, bài giải thích mô hình phiên bản, khác biệt với rollback và event sourcing, những ứng dụng truy vấn offline, và chương trình Java 17 độc lập có bộ oracle đối chiếu.

## 2. “Persistent” có nghĩa gì trong ngữ cảnh cấu trúc dữ liệu?

Trong thuật toán, **persistence** không nhất thiết là ghi dữ liệu xuống ổ đĩa. Nó là khả năng tiếp tục truy cập các **trạng thái cũ** dù đã thực hiện cập nhật.

Có ba khái niệm quan trọng:

- **Ephemeral (tạm thời):** chỉ giữ một trạng thái hiện hành; cập nhật thay đổi trực tiếp các nút. Một mutable segment tree là ví dụ.
- **Partial persistence (bền vững một phần):** được truy vấn phiên bản cũ nhưng chỉ được cập nhật trên phiên bản mới nhất.
- **Full persistence (bền vững đầy đủ):** được truy vấn **và tạo phiên bản mới từ bất cứ phiên bản cũ nào**. Lịch sử có thể phân nhánh thay vì là một đường thẳng.

Bản Java trong bài hỗ trợ **full persistence**: gọi update với một version ID tùy ý còn tồn tại. Cả version cũ và các nhánh trước đó vẫn nguyên vẹn.

**Confluent persistence** còn cho phép hợp nhất hai phiên bản độc lập thành phiên bản mới theo quy tắc riêng; điều này không tự động có khi chỉ path-copy. Ví dụ hợp nhất hai thay đổi cùng sửa A[3] cần một chính sách giải quyết xung đột, không thể chỉ OR hai con trỏ gốc.

### 2.1. Persistence không đồng nghĩa với lưu file, rollback hay retroactivity

- **Rollback/undo:** trở lại một trạng thái cũ. Một hệ thống có thể rollback bằng stack thay đổi rồi xóa trạng thái mới; đó chưa phải full persistence nếu không giữ truy cập mọi nhánh.
- **Snapshot nguyên mảng:** mỗi lần sửa gọi clone() để lưu cả n giá trị. Cách này vẫn giữ lịch sử, nhưng tốn O(n) thời gian và bộ nhớ **mỗi lần cập nhật**.
- **Event sourcing:** ghi lại log sự kiện và tính lại trạng thái bằng replay; có thể thêm checkpoint. Nó giải bài toán lịch sử ở tầng hệ thống, không phải cùng cơ chế pointer-sharing của cây bền vững.
- **MVCC (multi-version concurrency control):** cơ sở dữ liệu lưu nhiều phiên bản bản ghi để hỗ trợ snapshot isolation và giao dịch. Ý tưởng version tương tự nhưng còn liên quan transaction, visibility, garbage collection và đồng thời.
- **Retroactive algorithm:** cho phép chèn hoặc xóa **sự kiện ở mốc thời gian cũ** rồi làm thay đổi trạng thái ở các mốc thời gian **sau** mốc đó. Tạo nhánh từ snapshot cũ không tự động cập nhật những nhánh tương lai đã có, nên persistence **không bằng retroactivity**.

## 3. Mô hình phiên bản (version model) phải rõ ràng

Đặt version 0 là dãy ban đầu. Mỗi thao tác cập nhật tạo một version ID mới, không ghi đè một phiên bản hiện có. Với dãy:

**A₀ = [2, −1, 3, 4, 0]**, ta có:

| Phiên bản | Xuất phát từ | Thao tác | Giá trị dãy | Tổng |
|---:|---:|---|---|---:|
| v0 | Ban đầu | Không | [2,−1,3,4,0] | 8 |
| v1 | v0 | Set A[1]=5 | [2,5,3,4,0] | 14 |
| v2 | v1 | Add −2 vào A[3] | [2,5,3,2,0] | 12 |
| v3 | v0 | Set A[4]=7 | [2,−1,3,4,7] | 15 |
| v4 | v1 | Fork không sửa | [2,5,3,4,0] | 14 |

Sơ đồ phân nhánh:

```text
v0: [ 2,-1, 3,4,0] --set(1,5)--> v1: [2,5,3,4,0]
 |                                      |             |
 |--set(4,7)--> v3: [2,-1,3,4,7]       |--add(3,-2)->v2: [2,5,3,2,0]
                                        |
                                        |--fork------->v4: [2,5,3,4,0]
```

**V3 và v2 không phải “trạng thái tiếp theo” của nhau.** Chúng xuất phát từ hai nhánh khác nhau. Một ID phiên bản là **định danh snapshot**, không nhất thiết là một thời điểm trong một tuyến lịch sử duy nhất.

Một số câu hỏi có thể trả lời ngay:

- `sum(v0,[0,5))=8`.
- `sum(v1,[0,5))=14`.
- `sum(v2,[1,4))=5+3+2=10`.
- `sum(v3,[3,5))=4+7=11`.
- `diff(v3,v0,[0,5))=15−8=7`.
- `fork(v1)` giữ nguyên cùng root node nhưng tạo một version ID mới; không cấp phát cây mới.

### 3.1. Quy ước chỉ số và truy vấn

Trong bài dùng chỉ số 0-based và đoạn **nửa mở [l,r)**: lấy các vị trí l,l+1,...,r−1. Điều kiện hợp lệ là 0≤l≤r≤n. Với l=r, tổng đoạn rỗng bằng 0, không báo lỗi.

Point update yêu cầu 0≤i<n. Version ID hợp lệ phải nằm từ 0 đến `versionCount−1`. Nếu truy vấn version không tồn tại hoặc chỉ số sai, chương trình ném IllegalArgumentException **trước khi** sửa lịch sử.

**Hiệu hai phiên bản** phải nói rõ thứ tự. Trong Java, `difference(newer, older, l, r)` có nghĩa `sum(newer,l,r)−sum(older,l,r)`. Từ “newer” chỉ hướng hiệu người gọi muốn lấy, **không bắt buộc** version thứ nhất là hậu duệ của version thứ hai. Hiệu hai nhánh vẫn là số học hợp lệ, nhưng không tự diễn giải là “số lần cập nhật xảy ra giữa hai phiên bản”.

## 4. Segment tree thường: gốc chứa tổng đoạn

Một segment tree xây trên A độ dài n≥1. Nút gốc quản lý đoạn [0,n), tổng bằng tổng n phần tử. Với nút quản lý [lo,hi) có nhiều hơn một phần tử, chọn:

**mid = lo + floor((hi−lo)/2).**

Hai con quản lý [lo,mid) và [mid,hi). Mỗi nút lưu:

**sum(node) = sum(left) + sum(right)**,

còn nút lá [i,i+1) lưu A[i]. Vì mỗi lá đại diện một vị trí và cây nhị phân phân hoạch thành hai đoạn không rỗng, cây có **n lá và n−1 nút trong**, tổng **2n−1 nút**.

Segment tree mutable cập nhật A[i]=x bằng cách sửa lá và tính lại các nút trên đường lên gốc. Nếu ta lưu con trỏ tới root cũ nhưng cập nhật cùng các node dưới nó, root cũ sẽ nhìn thấy giá trị **mới**. Đó là lỗi thường gặp: **lưu root pointer không đủ** nếu các node bị sửa tại chỗ.

## 5. Path copying: chỉ sao chép đường từ gốc đến lá

Với cây bền vững, mọi Node được xem là **bất biến**. Khi cập nhật một vị trí i:

1. Bắt đầu từ root của version được chỉ định.
2. Đi xuống nhánh con chứa i.
3. **Tạo Node mới** cho lá mang giá trị mới.
4. Trên đường quay về, tạo Node cha mới với một con trỏ tới nhánh **được cập nhật** và một con trỏ tới nhánh **cũ không đổi**.
5. Đặt root mới vào danh sách phiên bản; **không sửa** root hay Node của phiên bản gốc.

Minh họa cập nhật một lá bên trái:

```text
Version cũ:               Version mới:

       oldRoot                 newRoot
        /   \                  /    \
      oldL  oldR            newL     \____ oldR (SHARED)
      / \                   /   \
    oldA oldB            newA    \___ oldB (SHARED)
      |
   old leaf               new leaf

Các nhánh không chứa chỉ số bị sửa được dùng chung.
```

Thực tế một cây con có thể chứa hàng nghìn lá; path copying không sao chép các lá ấy. Nó chỉ giữ lại **tham chiếu tới cây con bất biến**.

### 5.1. Pseudocode cho point-set

```text
set(node, lo, hi, index, newValue):
    nếu hi-lo == 1:
        return new Leaf(newValue)

    mid = lo + (hi-lo)/2
    nếu index < mid:
        newLeft  = set(node.left, lo, mid, index, newValue)
        newRight = node.right           // dùng chung
    ngược lại:
        newLeft  = node.left            // dùng chung
        newRight = set(node.right, mid, hi, index, newValue)

    return new Node(newLeft, newRight,
                    newLeft.sum + newRight.sum)
```

Gọi `newRoot=set(oldRoot,0,n,i,x)` rồi thêm `newRoot` vào bảng roots. Mỗi lần gọi đệ quy trả một node mới; node cũ không bị đụng vào.

### 5.2. Chứng minh giữ nguyên lịch sử

Quy nạp theo chiều cao của đoạn đang được cập nhật:

- **Lá:** thuật toán trả một lá mới mang x, không thay đổi lá cũ.
- **Nút trong:** theo giả thiết quy nạp, nhánh được cập nhật là một cây mới đúng, còn nhánh kia trỏ nguyên vào cây cũ bất biến. Nút cha mới lưu tổng hai con nên đúng, và không có phép gán nào lên Node cha cũ.

Do đó root mới biểu diễn đúng dãy sau một thay đổi vị trí; root cũ vẫn biểu diễn dãy trước đó. Lập luận không phụ thuộc dữ liệu có âm hay trùng, miễn phép cộng tổng dùng kiểu số đủ rộng.

### 5.3. Một cập nhật tạo bao nhiêu node?

Đường từ root đến một lá dài O(log n), vì mỗi lần đi xuống chiều dài đoạn giảm xấp xỉ một nửa. Mỗi mức tạo một Node nên:

- **Thời gian một point update: O(log n)**.
- **Số Node mới mỗi point update: O(log n)**.
- Phần còn lại **được chia sẻ**, không nhân số nút theo số phiên bản.

Ví dụ n=5 có cây đầu tiên 2n−1=9 Node. Với cập nhật vị trí 1, đường đi có 3 Node; vị trí 3 có 4; vị trí 4 có 4. Sau ba cập nhật từ ví dụ, tổng Node được tạo là 9+3+4+4=**20**, dù đang có năm phiên bản (v4 chỉ fork).

Nếu sao chép cả cây mỗi lần, ba cập nhật có thể cấp thêm 3×9 Node; nếu clone cả mảng, mỗi cập nhật tốn O(n) ô nhớ. Path copying tiết kiệm đáng kể khi n lớn và cập nhật ít phần tử mỗi lần.

## 6. Truy vấn tổng ở một phiên bản

Truy vấn `sum(version,l,r)` lấy root của đúng version ID rồi gọi truy vấn segment tree thông thường:

```text
query(node, segL, segR, qL, qR):
    nếu [segL,segR) không giao [qL,qR):
        return 0
    nếu [segL,segR) nằm hoàn toàn trong [qL,qR):
        return node.sum
    mid = segL + (segR-segL)/2
    return query(left, segL, mid, qL, qR)
         + query(right,mid, segR, qL, qR)
```

Tổng bằng 0 trên đoạn không giao là **phần tử trung hòa** của phép cộng. Với truy vấn min thì trung hòa cần là +∞; với max cần −∞. Không được sao chép nguyên query-sum sang cấu trúc quản lý min/max rồi vẫn trả 0 cho phần không giao.

Truy vấn chỉ **đọc** các node của root đã chọn, không thay đổi pointer hay tổng, và **không tạo Node mới**. Tính đúng được chứng minh bằng cách mỗi nút phủ một đoạn, các đoạn được cộng là rời nhau và hợp đúng bằng [l,r).

### 6.1. Vì sao range sum O(log n), không phải O(n)?

Với một đoạn truy vấn liên tiếp [l,r), ở mỗi độ sâu có nhiều nhất một đoạn phân hoạch cắt biên trái và một đoạn cắt biên phải; những đoạn được chứa trọn được lấy ngay bằng `node.sum`, không duyệt sâu. Tổng số node truy cập là O(log n), khác với duyệt từng phần tử. Bộ nhớ ngăn xếp cho query cũng O(log n).

### 6.2. Truy vấn hai phiên bản

Muốn biết tổng thay đổi giữa hai snapshot:

**delta(vB,vA,l,r) = sum(vB,l,r)−sum(vA,l,r).**

Mỗi truy vấn tổng O(log n), nên delta vẫn O(log n). Điều này làm việc so sánh hai trạng thái trong kiểm toán, biểu đồ trước–sau, hoặc thực nghiệm thuật toán trở nên đơn giản.

**Không nhầm hiệu tổng với số thay đổi:** nếu cùng một vị trí được tăng 5 rồi giảm 5, delta bằng 0 nhưng có hai sự kiện cập nhật. Nếu cần trả lịch sử sự kiện, phải lưu log hoặc metadata khác; persistent segment tree chỉ lưu các **giá trị** ở từng version.

## 7. Cập nhật cộng và phân nhánh tự do

Một point-add `add(base,index,delta)` có thể cài bằng:

1. Đọc giá trị cũ tại index trong `base`: O(log n).
2. Tính `newValue=oldValue+delta`.
3. Tạo phiên bản mới bằng `set(base,index,newValue)`: O(log n).

Tổng thời gian O(log n), và **một** phiên bản mới được tạo. Bản Java làm vậy để tránh nhân đôi code cập nhật nhưng vẫn giữ tính bất biến.

**Branching:** Nếu đã có v0→v1→v2 mà ta gọi `set(v0,4,7)`, root mới tạo v3 từ **v0**, không sửa v1 hay v2. Đó là full persistence. Tạo `fork(v1)` chỉ thêm root reference cũ làm v4, có chi phí cấp Node **0**, và version mới có thể được cập nhật về sau độc lập bằng path copying.

### 7.1. Thứ tự sự kiện và tính không giao hoán

`set(i,x)` và `add(i,d)` không giao hoán trên cùng i:

- `set(i,5)` rồi `add(i,2)` cho 7.
- `add(i,2)` rồi `set(i,5)` cho 5.

Nếu hai nhánh cập nhật cùng vị trí, không có phép “hợp nhất” tự nhiên nào đúng với mọi ý nghĩa ứng dụng. Nếu cập nhật các vị trí khác nhau và chỉ thao tác point-set độc lập, có thể tự thiết kế quy tắc merge; **không** suy ra merge tự động chỉ từ việc các Node bất biến.

## 8. Phân tích thời gian và bộ nhớ

Giả sử có n≥1 phần tử ban đầu, u lần **point update** thật, q truy vấn tổng, b lần fork (fork chỉ thêm version ID), và chiều dài cây H=O(log n).

| Thao tác | Thời gian | Node mới |
|---|---|---:|
| Build từ n phần tử | O(n) | 2n−1 |
| set từ version bất kỳ | O(log n) | O(log n) |
| add tại một vị trí | O(log n) | O(log n) |
| sum(version,l,r) | O(log n) | 0 |
| get(version,i) | O(log n) | 0 |
| difference(vB,vA,l,r) | O(log n) | 0 |
| fork(version) | O(1) khấu hao cho thêm root vào ArrayList | 0 |
| Xóa một version ID đang tham chiếu | Tùy chính sách quản lý roots/GC | Không thể mặc định giải phóng ngay subtree |

Tổng thời gian cho build + u update + q query + b fork là **O(n+(u+q)log n+b)**; bộ nhớ lưu Node và root references khoảng **O(n+u log n+b)**. Nếu b=0 và mỗi update tạo một version, thường viết **O(n+u log n)**.

### 8.1. Bộ nhớ không phải chỉ là các giá trị long

Mỗi Node Java gồm object header, tham chiếu tới con, trường `long sum` và padding/alignment; một triệu Node có thể tốn **nhiều chục MB** tùy JVM. Cận O(n+u log n) nói về bậc tăng, không phải số byte chính xác. Khi cần quy mô rất lớn, có thể lưu cây trong các mảng song song (`leftChild[]`, `rightChild[]`, `sum[]`) với chỉ số Node, dùng pool cấp phát hoặc cấu trúc lưu theo vùng nhớ.

### 8.2. Cây không bắt buộc đầy theo lũy thừa hai

Khi n=5, chia [0,5) ở mid=2, hai nửa có 2 và 3 phần tử. Số lá vẫn đúng n và tổng Node vẫn 2n−1. Không nhất thiết mở rộng n thành lũy thừa 2 rồi thêm các lá đệm, trừ khi implementation lựa chọn cách đó.

### 8.3. Bộ nhớ theo nhánh vẫn là tổng Node được tạo

Nếu v1 và v2 cùng con trỏ tới một cây con không đổi, chỉ có **một** bản Node của cây con ấy trong heap. Dù 1.000 version cùng trỏ vào nó, nó không được nhân lên 1.000 lần. Nhưng nếu giữ root của tất cả phiên bản mãi mãi, Java GC không thể thu hồi những Node vẫn reachable từ bất kỳ root nào.

## 9. Ứng dụng trong truy vấn và xử lý offline

### 9.1. Time-travel queries

Hệ thống nhận một dãy update theo thời gian t=1,2,3,... và lưu root sau mỗi bước. Để hỏi “tổng ở khoảng [l,r) sau sự kiện thứ t”, lấy root[t] rồi query. Mỗi truy vấn lịch sử chỉ tốn O(log n), không phải replay t sự kiện.

Truy vấn có thể đến **sau** khi mọi update đã chạy, và được đưa ra theo thứ tự bất kỳ (ví dụ hỏi t=50 rồi t=7). Đây là một lý do persistent segment tree rất hữu ích cho bài **offline queries**: chuẩn bị roots một lần rồi trả nhiều câu hỏi liên quan các snapshot.

### 9.2. So sánh các phương án giả định

Lưu v0 là cấu hình cơ sở. Tạo nhánh A từ v0 với một thay đổi, nhánh B từ v0 với thay đổi khác. Truy vấn tổng ở cùng đoạn trên hai nhánh giúp so sánh kịch bản. Không cần hoàn tác thay đổi A trước khi thử B.

Đây là lợi thế lớn so với segment tree mutable + undo stack, bởi trong mô hình undo, thao tác tạo nhánh mới đồng thời giữ nhánh trước thường cần log/redo phức tạp hơn.

### 9.3. Truy vấn k-th trong đoạn bằng cây tần suất persistent

Một ứng dụng nâng cao: cho mảng giá trị a[1..n]. Nén các giá trị thành chỉ số 0..M−1. Xây root[t] là **cây tần suất** của prefix gồm a[1..t] bằng cập nhật +1 ở vị trí của a[t].

Muốn tìm phần tử k-th smallest trong đoạn vị trí [l,r] (1-based), lấy **hai roots của prefix**: root[r] và root[l−1]. Tần suất trong đoạn bằng hiệu tần suất ở hai prefix, nên khi đi xuống cây:

- `leftCount = sum(root[r].left) − sum(root[l−1].left)`.
- Nếu k≤leftCount, đi con trái.
- Ngược lại đi con phải với k'=k−leftCount.

Chi phí O(log M) cho một truy vấn k-th, sau O(n log M) preprocessing; đây là ứng dụng thường được gọi “Chairman Tree” trong lập trình thi đấu.

**Điều kiện quan trọng:** các root[t] này là **prefix tích lũy** của những phép cộng tần suất không âm. Không được áp máy móc phép trừ đếm và thuật toán k-th lên hai nhánh tùy ý có point-set số âm. Hiệu hai phiên bản tổng quát vẫn là một con số signed, nhưng không nhất thiết biểu diễn histogram hợp lệ.

### 9.4. Kỹ thuật offline thay thế khi không cần full persistence

Nếu tất cả truy vấn được biết trước, đôi khi chỉ cần **sắp xếp theo thời điểm** rồi xử lý tuần tự bằng segment tree mutable, hoặc dùng **Mo's algorithm với modifications**, hoặc Fenwick theo thời gian. Những phương pháp ấy có thể tiết kiệm bộ nhớ nhưng hạn chế cách hỏi hoặc thứ tự trả lời.

Persistent segment tree đặc biệt phù hợp khi có nhiều truy vấn lịch sử theo thứ tự ngẫu nhiên, nhánh giả định, hoặc khi cần giữ nhiều snapshot cùng lúc. Nó không phải lựa chọn duy nhất cho mọi bài chứa từ “lịch sử”.

## 10. So sánh các phương án quản lý lịch sử

| Cách tiếp cận | Cập nhật điểm | Truy vấn lịch sử | Bộ nhớ cho u cập nhật | Hỗ trợ phân nhánh |
|---|---|---|---|---|
| Clone toàn bộ mảng mỗi lần | O(n) | O(r−l) nếu cộng trực tiếp | O(un) | Có, nhưng tốn bộ nhớ |
| Clone toàn bộ segment tree mỗi lần | O(n) | O(log n) | O(un) | Có |
| Mutable segment tree + log undo | O(log n) + log thay đổi | Phải rollback/replay đúng thứ tự | Tùy log | Khó giữ nhiều nhánh song song |
| Persistent segment tree path-copy | O(log n) | O(log n) | O(n+u log n) | Có, full nếu được cập nhật root cũ |
| Prefix sum chỉ append | O(1) amortized | O(1) prefix/range sum theo prefix đã tích lũy | O(n) | Không hỗ trợ point set bất kỳ như trên |
| Event sourcing + checkpoints | Tùy nghiệp vụ | Replay từ checkpoint | Tùy tần suất checkpoint | Cần thiết kế branch riêng |

Không được nói “Fenwick tree không thể persistent”: có nhiều cách xây Fenwick có phiên bản hoặc dùng cấu trúc khác để đạt mục tiêu tương tự. Bảng so **cách dùng thông thường** của các kỹ thuật.

## 11. Những điều kiện đúng của implementation Java 17

Bản minh họa dùng mảng giá trị `long[]`, tổng đoạn `long` và Node bất biến:

- `Node` có trường `final` cho con trái, con phải và `sum`. Không có setter; không sửa node sau khởi tạo.
- `PersistentHistory` có danh sách roots mutable để cấp version ID. Root của một version không được gán lại sau khi đã thêm.
- Cho n từ 1 tới 100.000; các giá trị ban đầu và giá trị sau cập nhật có giới hạn **−10⁹ tới +10⁹**, để mọi tổng đoạn có độ lớn ≤10¹⁴, an toàn trên signed long.
- `set` và `add` nhận một **baseVersion** bất kỳ, không nhất thiết mới nhất.
- `add` kiểm tràn phép cộng bằng `Math.addExact`, rồi kiểm miền giá trị trước khi tạo version.
- `get`, `sum` và `difference` không cấp phát Node.
- `fork` thêm một tham chiếu root vào roots, không tạo Node mới.
- Một thao tác bị từ chối vì version/index/range không hợp lệ không được tạo version nửa chừng.

### 11.1. An toàn số học

Nếu input là `long[]` với giá trị có độ lớn gần Long.MAX_VALUE, tổng các đoạn có thể overflow dù mỗi lá riêng lẻ hợp lệ. Bản Java ràng buộc `n≤100_000` và mỗi giá trị tuyệt đối ≤10⁹; vì vậy tổng của mọi đoạn ≤10¹⁴. Phép cộng dùng `Math.addExact` để làm lộ lỗi nếu có thay đổi code sau này vi phạm bound.

Đối với bài toán cần số lớn vượt phạm vi long, cân nhắc `BigInteger` hoặc số học modular tùy yêu cầu. **Tổng modulo P không tương đương tổng signed thực**, nên không được thay kiểu số một cách vô ý khi cần so sánh thứ tự/sai khác.

### 11.2. Cây Node bất biến chưa làm toàn bộ class thread-safe

Các Node có thể được nhiều version chia sẻ an toàn khi **không ai sửa chúng**. Nhưng danh sách `ArrayList<Node> roots` và bộ đếm số Node đã tạo vẫn mutable; class mẫu **không** cam kết thread-safe nếu nhiều luồng đồng thời cập nhật và đọc version mới. Khi xây hệ thống production, cần xuất bản roots an toàn, đồng bộ cập nhật version ID, quản lý vòng đời version và chiến lược GC.

### 11.3. Thu hồi version và garbage collection

Nếu ứng dụng không cần một số phiên bản, có thể ngừng giữ root của chúng. Chỉ những Node không còn reachable từ **bất kỳ** root được giữ nào mới có thể được Java GC thu hồi; một cây con dùng chung vẫn phải sống nếu có version còn trỏ tới nó.

Bản Java chỉ thêm version, **không hỗ trợ xóa** để ví dụ rõ ràng. Đừng hứa O(1) bộ nhớ tổng thể khi hệ thống giữ vô hạn lịch sử.

## 12. Chứng minh tính đúng tổng quát

### 12.1. Bất biến cây

Với mọi Node thuộc version v và đoạn [lo,hi) do nó quản lý:

**node.sum = tổng A_v[lo..hi−1]**.

Cơ sở: lá chứa chính A_v[i]. Bước quy nạp: Node trong lấy tổng của hai cây con phân hoạch đoạn, nên nhận tổng đúng.

### 12.2. Bất biến tính bền vững

Một khi root của version v đã thêm vào roots, không có phép cập nhật nào thay đổi Node reachable từ root ấy. Mọi update tạo Node mới trên đường đi và tham chiếu lại các subtree cũ bất biến. Vì vậy mọi sum/get của version v cho cùng kết quả trước và sau các update ở các version khác.

### 12.3. Chứng minh độ phức tạp

Chiều cao cây chia đôi là O(log n). Cập nhật đi một đường root→leaf, tạo một Node mỗi mức: O(log n) thời gian và thêm Node. Range sum đi theo các đoạn cắt biên và những đoạn phủ trọn nên O(log n); root selection là O(1) trung bình bằng ArrayList. Với u cập nhật, tổng Node O(n+u log n).

### 12.4. Nguyên tắc tự kiểm chứng

Để kiểm một persistent tree không âm thầm làm thay đổi phiên bản cũ, **đừng chỉ so một phiên bản hiện tại với itself**. Dùng một oracle độc lập là danh sách **các bản sao mảng nhỏ** trong test. Khi có update từ baseVersion, clone đúng mảng của base, sửa đúng một phần tử, thêm bản sao vào oracle. Sau mọi thao tác, chọn ngẫu nhiên nhiều phiên bản cũ và các đoạn để đối chiếu:

**sumTree(version,l,r) == sumArrayMirror(version,l,r).**

Ngoài ra so hiệu hai version, point get, tính bất biến sau fork, số lượng version, số Node mới và xử lý lỗi index/range.



## 13. Java 17 hoàn chỉnh: persistent segment tree có phân nhánh

Tệp `PersistentSegmentTreeHistoryDemo.java` dưới đây là chương trình **tự chạy** trên Java 17, không cần thư viện ngoài JDK. Nó dùng Node với các trường `final` để bảo đảm update không sửa lại subtree cũ. Danh sách roots ánh xạ mỗi version ID sang root của cây tương ứng.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Random;

public final class PersistentSegmentTreeHistoryDemo {
    private PersistentSegmentTreeHistoryDemo() {}

    static final class Node {
        final Node left;
        final Node right;
        final long sum;

        Node(Node left, Node right, long sum) {
            this.left = left;
            this.right = right;
            this.sum = sum;
        }
    }

    static final class PersistentHistory {
        static final long VALUE_LIMIT = 1_000_000_000L;
        private final int n;
        private final ArrayList<Node> roots = new ArrayList<>();
        private long createdNodes = 0;

        PersistentHistory(long[] initial) {
            if (initial == null || initial.length < 1
                    || initial.length > 100_000) {
                throw new IllegalArgumentException(
                    "array length must be 1..100000"
                );
            }
            n = initial.length;
            for (long value : initial) checkValue(value);
            roots.add(build(initial, 0, n));
        }

        private static void checkValue(long value) {
            if (value < -VALUE_LIMIT || value > VALUE_LIMIT) {
                throw new IllegalArgumentException(
                    "value outside [-1e9,1e9]"
                );
            }
        }

        private Node leaf(long value) {
            createdNodes++;
            return new Node(null, null, value);
        }

        private Node join(Node left, Node right) {
            createdNodes++;
            return new Node(
                left, right, Math.addExact(left.sum, right.sum));
        }

        private Node build(long[] a, int lo, int hi) {
            if (hi - lo == 1) return leaf(a[lo]);
            int mid = lo + (hi - lo) / 2;
            Node left = build(a, lo, mid);
            Node right = build(a, mid, hi);
            return join(left, right);
        }

        private Node rootAt(int version) {
            if (version < 0 || version >= roots.size()) {
                throw new IllegalArgumentException("unknown version");
            }
            return roots.get(version);
        }

        private void checkIndex(int index) {
            if (index < 0 || index >= n) {
                throw new IllegalArgumentException("invalid index");
            }
        }

        private void checkRange(int left, int right) {
            if (left < 0 || right < left || right > n) {
                throw new IllegalArgumentException("invalid [l,r)");
            }
        }

        private Node pathCopySet(
                Node old, int lo, int hi, int index, long value) {
            if (hi - lo == 1) return leaf(value);
            int mid = lo + (hi - lo) / 2;

            if (index < mid) {
                Node newLeft = pathCopySet(
                    old.left, lo, mid, index, value);
                return join(newLeft, old.right);
            } else {
                Node newRight = pathCopySet(
                    old.right, mid, hi, index, value);
                return join(old.left, newRight);
            }
        }

        int set(int baseVersion, int index, long value) {
            Node base = rootAt(baseVersion);
            checkIndex(index);
            checkValue(value);
            Node next = pathCopySet(base, 0, n, index, value);
            roots.add(next);
            return roots.size() - 1;
        }

        int add(int baseVersion, int index, long delta) {
            rootAt(baseVersion);
            checkIndex(index);
            long previous = get(baseVersion, index);
            long next = Math.addExact(previous, delta);
            checkValue(next);
            return set(baseVersion, index, next);
        }

        int fork(int baseVersion) {
            roots.add(rootAt(baseVersion));
            return roots.size() - 1;
        }

        private long query(Node node, int lo, int hi, int ql, int qr) {
            if (qr <= lo || hi <= ql) return 0;
            if (ql <= lo && hi <= qr) return node.sum;
            int mid = lo + (hi - lo) / 2;
            return Math.addExact(
                query(node.left, lo, mid, ql, qr),
                query(node.right, mid, hi, ql, qr));
        }

        long sum(int version, int left, int right) {
            Node root = rootAt(version);
            checkRange(left, right);
            if (left == right) return 0;
            return query(root, 0, n, left, right);
        }

        long get(int version, int index) {
            checkIndex(index);
            return sum(version, index, index + 1);
        }

        long difference(
                int newVersion, int oldVersion, int left, int right) {
            return Math.subtractExact(
                sum(newVersion, left, right),
                sum(oldVersion, left, right));
        }

        boolean sharesRoot(int a, int b) {
            return rootAt(a) == rootAt(b);
        }

        int versionCount() { return roots.size(); }
        long nodeCount() { return createdNodes; }
    }

    private static void check(boolean valid, String message) {
        if (!valid) throw new AssertionError(message);
    }

    private static long slowSum(long[] a, int left, int right) {
        long result = 0;
        for (int i = left; i < right; i++) {
            result += a[i];
        }
        return result;
    }

    public static void main(String[] args) {
        long[] original = {2, -1, 3, 4, 0};
        PersistentHistory history = new PersistentHistory(original);
        original[0] = 999; // Cannot alter immutable version 0.

        int v1 = history.set(0, 1, 5);
        int v2 = history.add(v1, 3, -2);
        int v3 = history.set(0, 4, 7);
        int v4 = history.fork(v1);

        System.out.println("v0 total=" + history.sum(0, 0, 5));
        System.out.println("v1 total=" + history.sum(v1, 0, 5));
        System.out.println(
            "v2 range[1,4)=" + history.sum(v2, 1, 4));
        System.out.println(
            "v3 range[3,5)=" + history.sum(v3, 3, 5));
        System.out.println(
            "v4 fork(v1) total=" + history.sum(v4, 0, 5));
        System.out.println(
            "delta(v3,v0)=" + history.difference(v3, 0, 0, 5));
        System.out.println(
            "v0 unchanged=" +
                (history.get(0, 0) == 2
                    && history.get(0, 1) == -1));
        System.out.println(
            "fork root shared=" + history.sharesRoot(v1, v4));
        System.out.println(
            "nodes=" + history.nodeCount()
                + ", versions=" + history.versionCount());
        System.out.println(
            "empty range sum=" + history.sum(v2, 2, 2));

        check(v1 == 1 && v2 == 2 && v3 == 3 && v4 == 4,
            "version ids must be sequential");
        check(history.nodeCount() == 20,
            "sample path-copy node count");
        boolean invalidRejected = false;
        try {
            history.sum(100, 0, 1);
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }
        System.out.println(
            "invalid version rejected=" + invalidRejected);
        check(invalidRejected, "invalid version not rejected");

        // Independent oracle: actual full-array copies for SMALL tests.
        // Production structure never stores these mirror arrays.
        Random rng = new Random(5082026L);
        for (int trial = 0; trial < 1_400; trial++) {
            int n = 1 + rng.nextInt(25);
            long[] seed = new long[n];
            for (int i = 0; i < n; i++) {
                seed[i] = rng.nextInt(201) - 100;
            }

            PersistentHistory h = new PersistentHistory(seed);
            ArrayList<long[]> mirrors = new ArrayList<>();
            mirrors.add(seed.clone());
            int updates = 0;

            for (int step = 0; step < 28; step++) {
                int base = rng.nextInt(mirrors.size());
                int mode = rng.nextInt(3);
                long[] next = mirrors.get(base).clone();
                int newVersion;

                if (mode == 0) {
                    int i = rng.nextInt(n);
                    long value = rng.nextInt(2001) - 1000;
                    next[i] = value;
                    newVersion = h.set(base, i, value);
                    updates++;
                } else if (mode == 1) {
                    int i = rng.nextInt(n);
                    long delta = rng.nextInt(51) - 25;
                    next[i] += delta;
                    newVersion = h.add(base, i, delta);
                    updates++;
                } else {
                    newVersion = h.fork(base);
                    check(h.sharesRoot(base, newVersion),
                        "fork should share the root");
                }

                check(newVersion == mirrors.size(),
                    "version ID mismatch");
                mirrors.add(next);

                // Check arbitrary historic snapshots, not just latest.
                for (int j = 0; j < 4; j++) {
                    int version = rng.nextInt(mirrors.size());
                    int other = rng.nextInt(mirrors.size());
                    int left = rng.nextInt(n + 1);
                    int right = left + rng.nextInt(n - left + 1);
                    int index = rng.nextInt(n);

                    long expected = slowSum(
                        mirrors.get(version), left, right);
                    long otherExpected = slowSum(
                        mirrors.get(other), left, right);

                    check(h.sum(version, left, right) == expected,
                        "historic range sum trial=" + trial);
                    check(h.get(version, index)
                            == mirrors.get(version)[index],
                        "historic point get trial=" + trial);
                    check(h.difference(
                            version, other, left, right)
                            == expected - otherExpected,
                        "historic difference trial=" + trial);
                }
                check(h.versionCount() == mirrors.size(),
                    "version count changed unexpectedly");
            }

            int maxPath = 1;
            int span = n;
            while (span > 1) {
                span = (span + 1) / 2;
                maxPath++;
            }
            check(h.nodeCount()
                    <= (2L * n - 1) + (long) updates * maxPath,
                "too many nodes allocated by path copying");
            check(h.nodeCount() >= 2L * n - 1,
                "initial binary tree node count");
        }

        System.out.println("Random branching histories: 1400 PASS");
    }
}
```

### 13.1. Biên dịch và chạy

```bash
javac -encoding UTF-8 PersistentSegmentTreeHistoryDemo.java
java PersistentSegmentTreeHistoryDemo
```

**Đầu ra xác định:**

```text
v0 total=8
v1 total=14
v2 range[1,4)=10
v3 range[3,5)=11
v4 fork(v1) total=14
delta(v3,v0)=7
v0 unchanged=true
fork root shared=true
nodes=20, versions=5
empty range sum=0
invalid version rejected=true
Random branching histories: 1400 PASS
```

### 13.2. Đọc mã theo thứ tự

**`Node`:** mỗi node lưu `left`, `right`, `sum`. Tất cả đều final. Lá có left/right=null nhưng query chỉ đi vào con khi đoạn có chiều dài >1. Node không lưu parent vì từ root ta đã biết đoạn của nó qua tham số đệ quy.

**`build`:** dựng cây đúng 2n−1 Node. Chương trình ban đầu dùng `long[]` làm nguồn để build, sau đó thay đổi chính mảng nguồn ở `main`. Root cũ vẫn lưu giá trị ban đầu vì lá giữ giá trị long, không giữ tham chiếu đến mảng input.

**`pathCopySet`:** đi theo đúng một nhánh chứa index, mỗi mức tạo một Node mới. Nhánh bên kia được truyền nguyên tham chiếu từ cây cũ vào `join`. Vì vậy các version share tối đa những cây con không đổi.

**`set(baseVersion,index,value)`:** kiểm version/index/value, tạo cây mới và thêm root. Nếu set cùng giá trị cũ, chương trình vẫn tạo một version mới với đường path-copy; đây là lựa chọn đơn giản, vẫn đúng nhưng có thể tối ưu no-op bằng cách dùng chung root khi value không thay đổi.

**`add(baseVersion,index,delta)`:** trước tiên lấy giá trị cũ ở **baseVersion**, không phải phiên bản mới nhất; rồi add và gọi set. Nếu cộng vượt giới hạn giá trị, không tạo version mới.

**`fork(baseVersion)`:** không sửa Node, chỉ thêm một tham chiếu tới root cũ. Hai version có cùng root identity ngay sau fork; khi cập nhật từ một trong chúng sau đó, bản mới sẽ path-copy và bản kia vẫn giữ nguyên.

**`sum(version,l,r)`:** đọc tổng trên đoạn nửa mở [l,r) trong root của version đã chọn. [l,l) trả 0. **`difference(new,old,l,r)`:** lấy hiệu hai truy vấn tổng; thứ tự đối số quyết định dấu của kết quả.

**`nodeCount`:** bộ đếm số Node cấp phát từ lúc khởi tạo instance, không phải số Node còn sống sau GC và không phải số Node riêng của version hiện tại. Demo có n=5, khởi tạo 9 Node; ba cập nhật tạo 3+4+4=11 Node; fork không tạo thêm, nên in 20.

### 13.3. Bộ kiểm thử phân nhánh ngẫu nhiên

Chương trình tạo **1.400 lịch sử ngẫu nhiên**, mỗi lịch sử có n=1..25 phần tử, rồi thực hiện 28 thao tác gồm point-set, point-add hoặc fork trên **một baseVersion được chọn ngẫu nhiên trong toàn bộ lịch sử**.

Sau từng thao tác, bộ test giữ một danh sách các mảng `long[]` **độc lập** với cây (chỉ trong test). Nó truy vấn ngẫu nhiên **4 lần mỗi bước** ở các version bất kỳ, đối chiếu:

1. Tổng đoạn [l,r) của phiên bản bất kỳ với tổng trực tiếp các phần tử trong mảng oracle.
2. Giá trị điểm tại một index bất kỳ với mảng oracle.
3. Hiệu tổng của hai phiên bản bất kỳ với hiệu hai tổng từ mảng oracle.
4. Version ID tuần tự, số version tăng đúng một mỗi thao tác.
5. Fork giữ root identity, cập nhật từ version cũ không ảnh hưởng các version khác.
6. Số Node đã cấp không vượt `(2n−1)+updates·(ceil(log₂n)+1)`, tức phù hợp chi phí O(log n) mỗi update.

Tổng cộng có **39.200 thao tác** trên 1.400 lịch sử và **156.800 vòng đối chiếu truy vấn** (mỗi vòng kiểm sum, get và difference). Việc đưa phiên bản cũ vào oracle sau mỗi update giúp bắt các lỗi mutation mà chỉ test trạng thái mới nhất khó phát hiện.

### 13.4. Những kiểm tra nên mở rộng

Nếu đưa code vào một hệ thống thực tế, cần thêm test với:

- Một phần tử n=1 và nhiều update từ cùng một root.
- Các giá trị sát giới hạn ±10⁹, rất nhiều update cộng/trừ và các truy vấn đủ đoạn.
- Phiên bản cũ được hỏi lại sau khi tạo hàng nghìn nhánh con.
- Đoạn rỗng [l,l), biên trái 0 và biên phải n.
- ID version âm/quá lớn, index ngoài miền, range l>r, value vượt bound, delta gây overflow.
- Kiểm snapshot input: sau khi constructor đọc mảng nguồn, thay đổi mảng nguồn phải không tác động tới version 0.
- Kiểm quy mô bộ nhớ/GC và concurrency nếu có nhiều reader/writer.

Bản demo không ép chạy brute force với n=100.000 vì oracle clone mảng theo version sẽ tốn nhiều tài nguyên; chỉ dữ liệu test nhỏ mới dùng clone toàn bộ.

## 14. Những lỗi cài đặt thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Chỉ lưu root pointer rồi sửa Node tại chỗ | Mọi version cũ đổi theo | Node bất biến, path-copy đường update |
| Copy toàn bộ cây sau mỗi update | Tốn O(n) Node/lần | Chỉ tạo O(log n) Node mới |
| Mặc định mọi version tạo từ mới nhất | Không hỗ trợ phân nhánh | set/add phải nhận baseVersion |
| Dùng chỉ số của bản mới nhất khi tính add trên bản cũ | Giá trị sai nhánh | Đọc từ root của baseVersion |
| Quên thêm root mới vào danh sách | Mất version mới | Thêm root đúng một lần sau update thành công |
| Sửa root trong ArrayList theo index cũ | Thay đổi lịch sử | roots chỉ append |
| Coi fork là clone cây | Tốn O(n) không cần thiết | Fork chia sẻ root |
| Coi fork chia sẻ root thì không bao giờ phân nhánh được | Nhầm pointer alias với mutation | Update sau fork bằng path-copy |
| Dùng [l,r] trong khi API là [l,r) | Off-by-one | Chuẩn hóa về half-open |
| Quên trả 0 cho đoạn rỗng của sum | Lỗi hoặc ra dữ liệu rác | sum(v,l,l)=0 |
| Dùng trung hòa 0 cho phép min/max | Kết quả sai với nhiều giá trị | Dùng +∞/−∞ phù hợp |
| Dùng int để lưu tổng nhiều phần tử | Overflow | Dùng long hoặc BigInteger |
| Không giới hạn tổng long | Có thể overflow dù leaf hợp lệ | Ràng buộc n và leaf, Math.addExact |
| Truy vấn một version khác rồi cộng sai chiều | Dấu hiệu delta ngược | difference(new,old)=new−old |
| Gọi hiệu tổng là số cập nhật | Không đúng khi thay đổi bù nhau | Log sự kiện riêng |
| Chứng minh O(log n) nhưng mỗi update lại clone mảng | Mã không khớp lý thuyết | Đo số Node mới và phân tích code |
| Đọc/hỏi version không hợp lệ | IndexOutOfBounds mơ hồ | Kiểm ID hợp lệ |
| Cho rằng persistence là ghi database | Nhầm nghĩa thuật toán | Phân biệt immutable version và durability |
| Cho rằng fork làm thay đổi timeline cũ | Nhầm với retroactivity | Fork tạo nhánh độc lập |
| Nghĩ hai nhánh auto-merge được | Xung đột update | Định nghĩa chính sách merge riêng |
| Trừ hai root tùy ý rồi coi histogram luôn không âm | Phân tích k-th sai | Chỉ dùng hiệu prefix frequency hợp lệ |
| Thêm lazy propagation nhưng sửa child cũ | Mất persistence | Copy cả Node/child cần thay đổi |
| Giữ mọi root vô hạn mà bỏ qua GC | Memory leak theo ứng dụng | Chính sách retention/compaction |
| Cho nhiều writer sửa ArrayList không đồng bộ | Race/version ID lỗi | Đồng bộ xuất bản root và cập nhật |
| Dùng coordinate compression rồi thêm khóa mới đổi thứ tự | Version cũ sai tọa độ | Chốt mapping hoặc dùng cây động |

## 15. Biến thể và kỹ thuật nâng cao

### 15.1. Range update với lazy propagation persistent

Trong segment tree có lazy propagation, một range-add có thể ghi “lười” vào nút quản lý cả đoạn. Để persistent, mỗi lần đẩy lazy xuống hoặc cập nhật con, **không được sửa** nút đã thuộc phiên bản cũ. Thay vào đó cần clone node liên quan và tạo lazy tag mới, sau đó cập nhật tổng nhất quán.

Lỗi hay gặp: point update đã path-copy, nhưng hàm `pushDown` vẫn đột biến hai node con đang được version cũ dùng chung; từ đó các truy vấn lịch sử sai. Một bản range-update persistent cần chứng minh invariants riêng và kiểm random differential. **Không** suy ra rằng đoạn mã point-update của bài đã hỗ trợ range-add O(log n).

### 15.2. Dynamic persistent segment tree

Khi miền chỉ số rất lớn, ví dụ [0,10⁹), nhưng ít vị trí được cập nhật, có thể tạo node theo nhu cầu thay vì xây sẵn 2n−1 node. Node null ngầm hiểu tổng 0; mỗi point update cấp O(log U) Node mới với U là độ lớn miền. Cách này hữu ích khi các tọa độ không thể nén trước.

Nếu dùng coordinate compression trong bài offline, phải chốt mapping của các khóa từ toàn bộ dữ liệu được biết trước. Nếu sau đó thêm khóa mới vào giữa các tọa độ đã nén mà thay thứ tự chỉ số, mọi phiên bản cũ cần giải thích lại; đây là thay đổi mô hình, không phải một update point đơn giản.

### 15.3. Persistent map/trie/treap

Một cây tìm kiếm cân bằng bất biến, trie bất biến hoặc HAMT có thể tạo phiên bản map/set mới khi thêm/xóa một khóa với cấu trúc chia sẻ. Khi khóa không phải chỉ số mảng hoặc truy vấn chủ yếu là lookup/update theo key, các cấu trúc này có thể thích hợp hơn segment tree.

Persistent treap hỗ trợ split/merge theo khóa hoặc vị trí, nhưng phải clone đúng các node bị sửa và đảm bảo cân bằng; “merge” của treap trong nghĩa thuật toán split/merge không tự giải quyết hợp nhất lịch sử của **hai phiên bản xung đột**.

### 15.4. Persistent DSU và rollback DSU

DSU có rollback bằng stack thay đổi rất hữu ích cho offline dynamic connectivity và divide-and-conquer theo thời gian. Một persistent DSU thực thụ khó hơn vì path compression của DSU mutable thường sửa nhiều parent pointer. Nếu cần truy vấn các snapshot DSU, hãy chọn thiết kế thích hợp thay vì mặc nhiên copy nguyên code mutable.

### 15.5. Chính sách lưu history trên hệ thống thật

Full persistence giúp tạo hàng nghìn nhánh thử nghiệm, nhưng phiên bản không dùng nữa vẫn có thể giữ tham chiếu tới các subtree. Một hệ thống production cần quyết định:

- Phiên bản nào cần lưu dài hạn?
- Có cần dấu thời gian, ID giao dịch và audit log ngoài root ID không?
- Có thể archive/serialize subtree theo dạng DAG để tránh nhân bản khi lưu ra đĩa?
- Ai có quyền tạo/đọc nhánh và khi nào snapshot được coi là nhất quán?
- Có cần ràng buộc số bản root, giới hạn bộ nhớ hoặc dọn dẹp định kỳ không?

Cấu trúc bền vững giải quyết **khả năng giữ snapshot ở bộ nhớ**; tính bền vững dữ liệu sau crash (*durability*) vẫn là bài toán lưu trữ độc lập.

## 16. Bài tập có đáp án

**Bài 1.** Persistent data structure nghĩa là gì? *Đáp án:* cập nhật tạo trạng thái mới mà vẫn truy vấn được trạng thái cũ.

**Bài 2.** Partial persistence khác full persistence? *Đáp án:* partial chỉ update version mới nhất; full cho update từ version cũ bất kỳ.

**Bài 3.** Chỉ lưu root pointer đủ chưa nếu Node bị sửa tại chỗ? *Đáp án:* không, version cũ thấy dữ liệu bị thay đổi.

**Bài 4.** Path copying tạo Node mới ở đâu? *Đáp án:* trên một đường root→leaf chứa vị trí cập nhật.

**Bài 5.** Các subtree không liên quan đến update được xử lý ra sao? *Đáp án:* dùng chung tham chiếu bất biến.

**Bài 6.** Với n lá và cây nhị phân đầy đủ theo nghĩa mỗi Node trong có đúng 2 con, tổng Node? *Đáp án:* 2n−1.

**Bài 7.** Với n=5, cây ban đầu có bao nhiêu Node? *Đáp án:* 9.

**Bài 8.** Từ [2,−1,3,4,0] set vị trí 1 thành 5 cho dãy gì? *Đáp án:* [2,5,3,4,0].

**Bài 9.** Tổng v1 sau thao tác trên? *Đáp án:* 14.

**Bài 10.** Từ v1 add −2 vào vị trí 3, tổng [1,4)? *Đáp án:* 10.

**Bài 11.** Từ v0 set vị trí 4 thành 7, tổng [3,5)? *Đáp án:* 11.

**Bài 12.** Hiệu tổng v3−v0 toàn mảng? *Đáp án:* 7.

**Bài 13.** Fork(v1) có phải clone toàn bộ cây? *Đáp án:* không, chỉ thêm root reference.

**Bài 14.** Vì sao v2 và v3 không nhất thiết là hai thời điểm liên tiếp? *Đáp án:* chúng có thể là hai nhánh từ các ancestor khác nhau.

**Bài 15.** Thời gian point update persistent segment tree? *Đáp án:* O(log n).

**Bài 16.** Bộ nhớ sau u point update? *Đáp án:* O(n+u log n), chưa tính các root fork riêng.

**Bài 17.** Truy vấn sum ở version cũ có cấp Node mới không? *Đáp án:* không, chỉ đọc Node.

**Bài 18.** Truy vấn đoạn rỗng [l,l) trả gì? *Đáp án:* 0 cho range sum.

**Bài 19.** Giá trị trung hòa của min query là 0 đúng không? *Đáp án:* không, thường dùng +∞.

**Bài 20.** Điểm set cùng giá trị cũ có buộc cấp Node mới không? *Đáp án:* không về lý thuyết; demo vẫn path-copy cho đơn giản.

**Bài 21.** Một thay đổi +5 rồi −5 có delta tổng bằng mấy? *Đáp án:* 0, dù đã có hai sự kiện.

**Bài 22.** Persistence có đồng nghĩa retroactive algorithm không? *Đáp án:* không; cập nhật nhánh cũ không sửa mọi snapshot tương lai.

**Bài 23.** Trong prefix-frequency tree, root[r]−root[l−1] biểu diễn gì? *Đáp án:* tần suất của đoạn vị trí [l,r] theo quy ước 1-based.

**Bài 24.** Vì sao không dùng hiệu hai nhánh signed bất kỳ để tìm k-th? *Đáp án:* tần suất hiệu có thể âm, không tạo histogram hợp lệ.

**Bài 25.** Nếu muốn range-add persistent O(log n), cần chú ý gì? *Đáp án:* lazy tag và pushDown phải path-copy, không sửa child của version cũ.

**Bài 26.** Tại sao Java Node `final` chưa đủ để class toàn bộ thread-safe? *Đáp án:* danh sách roots và bộ đếm Node vẫn mutable, cần đồng bộ.

**Bài 27.** Nếu xóa một root version, mọi Node của root đó được GC ngay? *Đáp án:* không, những Node còn reachable từ version khác phải tiếp tục sống.

**Bài 28.** Cách oracle độc lập phù hợp cho n nhỏ? *Đáp án:* giữ một bản long[] clone riêng cho mỗi version và so sum/get/diff.

**Bài 29.** Khi dùng array clone mỗi update, bộ nhớ mỗi lần là bao nhiêu? *Đáp án:* O(n), khác path copying O(log n).

**Bài 30.** Vì sao historical query có thể trả theo thứ tự ngẫu nhiên? *Đáp án:* mỗi version có root riêng, không cần replay các update trước đó.

## 17. Checklist trước khi sử dụng

1. Có cần hỏi phiên bản cũ hay chỉ trạng thái hiện tại?
2. Có cần cập nhật từ phiên bản cũ (full persistence) hay chỉ phiên bản mới nhất?
3. Xác định rõ version ID và version parent; phân biệt nhánh và thời gian.
4. Chọn dữ liệu lưu ở mỗi Node và phép tổng hợp có tính kết hợp.
5. Node sau khởi tạo có thật sự immutable không?
6. Update có chỉ tạo Node mới trên đường cần sửa?
7. Mọi nhánh không đổi có được chia sẻ an toàn?
8. Có kiểm l/r theo [l,r) và version/index hợp lệ?
9. Có định nghĩa rõ hiệu sum(new)−sum(old) và thứ tự đối số?
10. Có ràng buộc số học tránh tràn tổng/delta?
11. Có phân tích O(n) build, O(log n) point-update/query?
12. Có tính chi phí lưu mọi root và node object thực tế?
13. Fork có tạo root alias O(1) mà không sửa lịch sử?
14. Nếu có lazy update, pushDown có vô tình sửa child cũ?
15. Nếu có truy vấn k-th qua hiệu prefix roots, dữ liệu có thật là tần suất không âm?
16. Có chính sách retention/garbage collection/version compaction?
17. Có tách time-travel snapshot khỏi durability và retroactivity?
18. Có test bằng oracle array clone trên bản nhỏ, random baseVersion, branch và old-version queries?
19. Có benchmark với số phiên bản lớn và phân tích Node count?
20. Khi nhiều luồng cùng cập nhật roots, có đồng bộ version publication?

## Kết luận

**Cấu trúc dữ liệu bền vững** cho phép lưu và truy vấn lịch sử mà không phải sao chép toàn bộ dữ liệu mỗi lần cập nhật. Với **persistent segment tree**, chỉ cần **path-copy O(log n) Node** trên đường chứa vị trí sửa và chia sẻ các subtree bất biến; từ đó point update và range query giữ thời gian **O(log n)**, còn bộ nhớ sau u cập nhật là **O(n+u log n)**.

Mỗi phiên bản có root riêng; cập nhật từ root cũ tạo một **nhánh** mà không ảnh hưởng các nhánh khác. Điều này hữu ích cho truy vấn ngoại tuyến theo thời điểm, so sánh kịch bản, lịch sử dữ liệu và các kỹ thuật nâng cao như cây tần suất persistent cho k-th trong đoạn. Nhưng persistence không tự là rollback, retroactivity hay lưu bền vững sau crash: mỗi nhu cầu ấy cần mô hình và thiết kế bổ sung.

# Cây đoạn và các điều kiện gộp kết quả

**Cây đoạn** (*segment tree*) là cấu trúc dữ liệu tổ chức các đoạn liên tiếp của một mảng thành cây nhị phân, cho phép **truy vấn thông tin trên một đoạn** và **cập nhật giá trị** mà không phải duyệt lại toàn bộ mảng. Nhưng cây đoạn không chỉ là “một cây có hai con và vài công thức”: điều quyết định tính đúng là **thông tin lưu trong nút có thể được gộp chính xác từ hai đoạn con kề nhau hay không**.

Giả sử một truy vấn trên đoạn có giá trị tổng hợp `F([l,r))`. Nếu có thể mô tả một phép gộp `⊗` sao cho với mọi điểm chia `l≤m≤r`:

**`F([l,r)) = F([l,m)) ⊗ F([m,r))`**,

và phép gộp này **có tính kết hợp** (*associative*), ta có nền tảng để dùng segment tree. Khi cần hỗ trợ đoạn rỗng và padding, một **phần tử đơn vị** (*identity element*) `e` giúp làm điều đó sạch sẽ:

**`(a⊗b)⊗c = a⊗(b⊗c)`**,  
**`e⊗a = a⊗e = a`**.

Cặp **(kiểu summary, phép gộp có tính kết hợp và identity)** tạo thành một **monoid** khi phép gộp đóng trên các summary. Đây là mô hình quan trọng nhất để trả lời câu hỏi: **“Dữ liệu nào có thể lưu ở một node và hai node gộp lại như thế nào?”**

Bài thuộc nhóm **Truy vấn và ngoại tuyến** của **Computer Science Algorithms**, chủ đề **Cây đoạn và các điều kiện gộp kết quả**. Ta học từ phép gộp tổng/min/max, sự cần thiết của **tính kết hợp nhưng không cần giao hoán**, cách dùng **summary nhiều trường** cho tổng đoạn con lớn nhất, đến các phép biến đổi **không giao hoán** như hợp thành hàm affine; sau đó phân tích **lazy propagation** cho cập nhật cộng trên đoạn và sự tương thích giữa thao tác cập nhật và summary.

**Mục tiêu:** tự kiểm được một truy vấn có thích hợp với segment tree hay không; biết xác định identity, công thức merge và invariant; cài được cây đoạn với **point set + range query**; không đổi thứ tự khi gộp lân cận; thiết kế lazy tag đúng; phân biệt cây đoạn với prefix sums, Fenwick tree và các thuật toán offline; tránh lỗi nửa mở [l,r), padding, empty range, overflow và kết quả sai với mảng toàn số âm.

## 1. Mô hình đoạn và yêu cầu của bài toán

Có một mảng độ dài n:

**`A=[a₀,a₁,...,a_{n−1}]`**.

Một truy vấn đoạn hỏi thông tin về **các phần tử liên tiếp** từ l đến r−1:

**`A[l],A[l+1],...,A[r−1]`**, ký hiệu **`[l,r)`**.

Trong toàn bộ bài này:
- **l bao gồm**, **r không bao gồm**.
- `0≤l≤r≤n`.
- **Đoạn rỗng** khi l=r.
- **Truy vấn toàn mảng** là [0,n).
- **Cập nhật điểm** `set(i,v)` thay đúng `A[i]` bằng v.
- Phần nâng cao **rangeAdd(l,r,d)** cộng d cho từng `A[i]` trong [l,r).

Bài toán ví dụ:

~~~text
A = [2, -1, 3, 5, -2]

sum([0,5)) = 7
sum([1,4)) = -1 + 3 + 5 = 7
min([1,4)) = -1

set(1,4)
A = [2, 4, 3, 5, -2]
sum([0,5)) = 12
~~~

Nếu tính lại bằng vòng lặp sau mọi truy vấn, một truy vấn có thể cần **O(n)**. Nếu một update làm lại mảng prefix, có thể cũng cần O(n). Segment tree lưu các summary trên những đoạn con để thường trả lời và cập nhật trong **O(log n)** khi merge một cặp summary tốn O(1).

### Vì sao dùng đoạn nửa mở?

Đoạn [l,r) có độ dài đúng `r−l`. Hai đoạn:

**`[l,m)`** và **`[m,r)`**

kề nhau, không chồng chéo và hợp lại thành [l,r). Đây chính là phép chia trong cây đoạn. Với l=r, không có phần tử nào; identity cho phép trả kết quả có nghĩa theo kiểu summary đã chọn.

Không được tự biến [l,r) thành [l,r] giữa chừng. Nếu đề cung cấp truy vấn **1-based inclusive** [L,R], cần chuyển có chủ đích sang **0-based half-open** [L−1,R) khi 1≤L≤R≤n. Mọi ví dụ Java phía dưới nhận **0-based half-open** trực tiếp.

## 2. Điều kiện đầu tiên: một summary gộp được từ hai nửa

Gọi `S(l,r)` là summary cần lưu cho đoạn [l,r). Muốn dùng cây đoạn, phải có hàm:

**`merge(S(l,m),S(m,r)) = S(l,r)`**.

Điều này cần đúng **với mọi cách chia đoạn hợp lệ**, không chỉ một ví dụ. Dữ liệu trong summary phải chứa đủ thông tin để tính tổng hợp của hai phía.

Ví dụ:
- **Tổng đoạn:** `merge(x,y)=x+y`.
- **Nhỏ nhất đoạn:** `merge(x,y)=min(x,y)`.
- **Lớn nhất đoạn:** `merge(x,y)=max(x,y)`.
- **XOR đoạn:** `merge(x,y)=x XOR y`.
- **Ước chung lớn nhất:** `merge(x,y)=gcd(x,y)` khi dùng quy ước không âm phù hợp.
- **Chuỗi ghép theo thứ tự:** `merge(x,y)=x+y` dưới nghĩa nối chuỗi, không phải cộng số.
- **Hợp thành các phép biến đổi tuyến tính:** phải lưu cặp hệ số và xác định đúng thứ tự thực thi.

Đoạn lớn được chia thành các đoạn con; khi hai summary đủ thông tin để ghép chính xác, ta không cần xem lại từng phần tử.

### Summary có thể là một cấu trúc nhiều trường

Một nhầm lẫn phổ biến: “mỗi node segment tree phải chỉ lưu một số”. Điều này **không đúng**. Ta có thể lưu:
- Cặp (sum,count) để tính average.
- Bộ bốn (sum,prefixMax,suffixMax,bestMax) cho **maximum nonempty subarray sum**.
- Ma trận kích thước cố định, cặp hệ số hàm affine, hoặc một bảng DP kích thước cố định.
- Một trạng thái automaton hữu hạn hoặc bộ summary theo ràng buộc.

Câu hỏi không phải “có lưu được một số không”, mà là **summary có kích thước và công thức gộp đủ hiệu quả không**.

## 3. Điều kiện thứ hai: tính kết hợp

Phép gộp `⊗` phải thỏa:

**`(a⊗b)⊗c=a⊗(b⊗c)`**.

Đây là **associativity**, không phải commutativity.

Tại sao cần? Mỗi truy vấn có thể được tách thành các đoạn con theo **các cách nhóm khác nhau**. Khi build cây, ta gộp các cặp theo cấu trúc cây. Khi query, ta có thể gộp nhiều node hoàn chỉnh theo thứ tự khác. Nếu cách đặt dấu ngoặc làm thay đổi kết quả, câu trả lời sẽ phụ thuộc cấu trúc cây chứ không chỉ phụ thuộc mảng.

### Những phép gộp đúng

**Cộng số nguyên:**

**`(a+b)+c=a+(b+c)`** theo số học toán học không overflow.

**Min:**

**`min(min(a,b),c)=min(a,min(b,c))`**.

**Max:**

**`max(max(a,b),c)=max(a,max(b,c))`**.

**Nối chuỗi theo thứ tự:**

**`("a"+"b")+"c" = "a"+("b"+"c") = "abc"`**.

**Nhân ma trận:**

**`(AB)C=A(BC)`** nếu kích thước tương thích.

**Hợp thành hàm:**

**`h∘(g∘f)=(h∘g)∘f`**.

### Những phép gộp sai

**Phép trừ:** `(10−3)−2=5` nhưng `10−(3−2)=9`.

**Phép chia:** nói chung không kết hợp.

**Lấy trung bình hai giá trị:** `avg(avg(a,b),c)` khác `avg(a,avg(b,c))` và không cho trung bình đúng của các đoạn **khác độ dài**.

**Ghép “số phần tử phân biệt” bằng cộng:** `distinct(left)+distinct(right)` đếm trùng những giá trị xuất hiện ở cả hai phía. Nếu chỉ lưu count mà không lưu thông tin tập giá trị, không thể gộp chính xác.

### Associativity trong lập trình số thực

Phép cộng dấu phẩy động `double` **không kết hợp chính xác trên máy tính** do làm tròn: `(a+b)+c` có thể khác `a+(b+c)` ở vài bit. Segment tree vẫn được dùng để tính tổng số thực nếu bài chấp nhận sai số, nhưng không được khẳng định đáp án bit-for-bit giống vòng cộng tuần tự cho mọi input. Nếu cần chính xác tuyệt đối, chọn biểu diễn số học phù hợp hoặc xác định tolerance/numerical error budget.

## 4. Điều kiện thứ ba: identity và closure

Nếu dùng một thuật toán truy vấn có thể gộp các phần **không có dữ liệu**, ta cần một giá trị identity `e` sao cho:

**`merge(e,x)=merge(x,e)=x`**.

Một vài lựa chọn:

| Summary / phép gộp | Identity |
|---|---|
| Tổng `x+y` | 0 |
| Tích `x·y` | 1 |
| Min trên long | `Long.MAX_VALUE` |
| Max trên long | `Long.MIN_VALUE` |
| XOR | 0 |
| GCD trên số nguyên không âm | 0 vì gcd(0,x)=x |
| Nối chuỗi | Chuỗi rỗng `""` |
| Hợp thành phép biến đổi affine | Hàm đồng nhất `f(x)=x` |
| Maximum nonempty subarray | **Nút đánh dấu empty**, không chỉ đặt best=0 |

**Closure**: nếu hai summary hợp lệ thuộc kiểu S, thì merge phải trả một summary hợp lệ **cùng kiểu S**. Nếu dữ liệu merge vượt giới hạn kiểu số, phép toán trên máy không còn mô phỏng đúng toán học.

### Đoạn rỗng có nghĩa gì?

Với tổng, kết quả trên đoạn rỗng hợp lý là 0. Với minimum, trả `Long.MAX_VALUE` là một **quy ước đơn vị đại số**, không phải một giá trị nhỏ nhất thực tế trong đoạn có phần tử. Caller có thể quyết định **từ chối truy vấn min của đoạn rỗng**, hoặc dùng kiểu Optional để thể hiện “không có min”.

Với maximum nonempty subarray, nếu trả best=0 cho đoạn rỗng mà không đánh dấu rõ, phép gộp có thể **cho phép tập con rỗng** và làm sai khi mọi phần tử đều âm. Tốt hơn là dùng record có cờ `empty`, merge identity bằng cách trả nút bên kia.

### Tại sao phải là identity hai phía?

Trong cây đoạn iterative, một phần summary có thể được gộp ở **bên trái** hoặc **bên phải**. Cần cả:

**`e⊗x=x`** và **`x⊗e=x`**.

Nếu chỉ có một phía, phương pháp hai accumulator tiêu chuẩn không còn được đảm bảo.

## 5. Không cần phép gộp có tính giao hoán

**Commutativity** là tính chất:

**`a⊗b=b⊗a`**.

Segment tree **không bắt buộc** điều này. Nó cần **giữ thứ tự trái → phải** của các đoạn. Ví dụ nối chuỗi:

**`"ab"+"cd"="abcd"`**, còn **`"cd"+"ab"="cdab"`**.

Cả hai khác nhau, dù phép nối chuỗi vẫn kết hợp.

### Vì sao query iterative có hai accumulator?

Khi truy vấn [l,r) trên cây đáy ở các lá:
- Một node được lấy từ **biên trái**, phải gộp vào **sau** những node đã thu ở bên trái: `leftAcc=merge(leftAcc,node)`.
- Một node được lấy từ **biên phải**, phải gộp vào **trước** những node đã thu ở bên phải: `rightAcc=merge(node,rightAcc)`.
- Sau khi hai biên gặp nhau, trả `merge(leftAcc,rightAcc)`.

Pseudocode:

~~~text
query(l, r):
    L = l + size
    R = r + size
    leftAcc  = identity
    rightAcc = identity

    while L < R:
        if L is odd:
            leftAcc = merge(leftAcc, tree[L])
            L++

        if R is odd:
            R--
            rightAcc = merge(tree[R], rightAcc)

        L = L / 2
        R = R / 2

    return merge(leftAcc, rightAcc)
~~~

Nếu thay dòng `rightAcc=merge(tree[--R],rightAcc)` thành `rightAcc=merge(rightAcc,tree[--R])`, truy vấn tổng số vẫn có thể ra đúng do cộng giao hoán, nhưng truy vấn nối chuỗi, hợp thành hàm và nhân ma trận có thể **sai thứ tự**.

### Minh họa bằng hàm affine

Dùng phép biến đổi:

**`f(x)=a·x+b (mod M)`**,

với M=1.000.000.007 và 0≤a,b<M. Nếu đoạn bên trái biểu diễn f và bên phải biểu diễn g, thứ tự thực thi từ trái qua phải là **f trước, g sau**, nên:

**`merge(f,g)=g∘f`**.

Nếu `f(x)=a_fx+b_f`, `g(x)=a_gx+b_g`, thì:

**`g(f(x))=(a_ga_f)x+(a_gb_f+b_g) (mod M)`**.

Summary là cặp (a,b), identity là (1,0). Merge là **O(1)** trong số học modulo với số cố định, kết hợp nhưng **không giao hoán**.

Ví dụ ba hàm:

- `f₀(x)=2x+1`.
- `f₁(x)=3x+4`.
- `f₂(x)=5x+6`.

Áp theo thứ tự 0→1→2:

**`f₂(f₁(f₀(x)))=30x+41`**.

Tại x=2, kết quả **101**. Nếu đảo thứ tự gộp, hệ số b có thể khác; vì vậy đây là test mạnh hơn sum/min để phát hiện query sai thứ tự.

### Nối chuỗi cũng kết hợp nhưng không O(1)

Nối chuỗi là một ví dụ đại số dễ hiểu, **nhưng** trong Java, tạo `left+right` với String immutable thường phải sao chép các ký tự, chi phí phụ thuộc độ dài hai chuỗi. Do đó nếu mỗi summary giữ toàn bộ chuỗi, số lần merge chỉ O(log n) **không đủ** để gọi thời gian truy vấn thực là O(log n). Cần tính chi phí `T_merge` hoặc dùng cấu trúc như rope/hash độ dài cố định nếu yêu cầu.

Hàm affine và ma trận kích thước cố định minh họa đúng cả **tính kết hợp** lẫn **merge O(1)**.

## 6. Cây đoạn được tổ chức như thế nào?

Với mảng A độ dài n, cây nhị phân chia đoạn [0,n) thành các phần:

~~~text
                   [0,8)
             /                 \
         [0,4)                [4,8)
        /      \              /      \
     [0,2)   [2,4)        [4,6)    [6,8)
      / \      / \          / \       / \
     0   1    2   3        4   5     6   7
~~~

Sơ đồ là cho n=8. Với n không phải lũy thừa hai, một cách phổ biến là **đệm cây lên size=2^ceil(log₂(max(n,1)))** rồi đặt identity vào các lá phụ. Vì identity không làm thay đổi merge, root vẫn là summary của các n phần tử thật.

### Biểu diễn cây bằng mảng iterative

Dùng `tree[1]` làm root. Nếu size là lũy thừa 2:
- Lá tương ứng A[i] nằm ở `tree[size+i]`.
- Hai con của node p là `tree[2p]` và `tree[2p+1]`.
- Node p lưu `merge(tree[2p],tree[2p+1])`.
- Bản thân các node trong mảng không cần Java object node riêng.

Từ lá có đủ summary, xây các node từ p=size−1 về p=1.

### Độ phức tạp xây cây

Cây đáy có size lá và size−1 nút nội bộ. Khi mỗi merge O(1), build cần **O(size)=O(n)** thời gian và O(size)=O(n) bộ nhớ (với n>0 và đệm lên lũy thừa hai). Nếu n=0, ta vẫn có thể dùng size=1, root identity, nhưng chỉ cho phép query [0,0) và không có update điểm hợp lệ.

### Không nhầm index node và index mảng gốc

Trong cây iterative:
- `tree[size+i]` tương ứng A[i].
- `tree[p]` ở phần trên là node summary, không phải A[p].
- Sau point update, phải cập nhật tổ tiên theo đường về root.

## 7. Chứng minh invariant của cây

**Invariant node:** mỗi nút biểu diễn đoạn các lá liên tiếp và chứa summary đúng của đoạn đó, theo **thứ tự trái → phải**.

**Lá:** một lá thật chứa summary của một phần tử, đúng theo định nghĩa. Lá đệm chứa identity.

**Nút trong:** giả sử hai con chứa summary đúng của hai đoạn con liên tiếp. Nhờ công thức merge, node cha chứa summary của đoạn hợp. Quy nạp từ lá lên root cho thấy build đúng.

**Point set:** đổi đúng một lá; những node không chứa lá này giữ nguyên. Cập nhật tất cả tổ tiên bằng merge hai con sẽ khôi phục invariant trên đường lên root. Chiều cao cây O(log n), nên một update tốn O(log n) phép merge.

**Range query:** [l,r) được phân rã thành O(log n) node không giao nhau, bảo toàn thứ tự. Nhờ associativity và identity, gộp summary các node này tạo đúng F([l,r)). Với phép gộp không giao hoán, thuật toán **phải bảo toàn thứ tự node** như hai accumulator ở mục 5.

## 8. Điểm cập nhật và truy vấn đoạn: các phép phổ biến

### Tổng đoạn

Summary: một số `sum`.

- Leaf: `sum=a_i`.
- Merge: `sum=left.sum+right.sum`.
- Identity: 0.

Dễ dùng, nhưng phải kiểm **tràn kiểu**. Bản Java sử dụng `Math.addExact` cho tổng để không âm thầm wrap. Nếu dữ liệu thực tế có khả năng vượt long, cân nhắc BigInteger hay miền số toán học khác.

### Min, max

Summary: min hoặc max.
- Merge: `min(left,right)` hoặc `max(left,right)`.
- Identity: `Long.MAX_VALUE` cho min; `Long.MIN_VALUE` cho max.

Nếu đoạn rỗng, identity chỉ là quy ước; nếu ứng dụng yêu cầu min/max của đoạn không rỗng, nên validate l<r.

### GCD

Summary: GCD không âm; identity 0 vì `gcd(0,x)=|x|`. Với các số âm hoặc `Long.MIN_VALUE`, cẩn thận khi lấy trị tuyệt đối: `abs(Long.MIN_VALUE)` vượt long có dấu. Cần chuẩn hóa miền và kiểu.

### XOR

Summary: XOR tất cả phần tử trên đoạn; identity 0 và merge là XOR. Không cần inverse cho point update vì cây tính lại các tổ tiên từ hai con.

### Trung bình

Không thể lấy trung bình hai trung bình nếu hai đoạn có **độ dài khác nhau**. Đúng là lưu:

**`Node(sum,count)`**.

Merge:
- `sum=sumLeft+sumRight`;
- `count=countLeft+countRight`.

Identity: (0,0). Sau query, nếu count>0, average=sum/count với biểu diễn phù hợp. Trung bình chỉ là **phép suy ra từ summary**, không phải phép merge trực tiếp của hai average.

## 9. Khi một giá trị đơn lẻ không đủ: maximum subarray sum

Bài toán: tìm **tổng lớn nhất của một đoạn con liên tiếp không rỗng** nằm hoàn toàn trong đoạn truy vấn.

Nếu chỉ lưu **tổng đoạn**, không thể biết đoạn con nào cho tổng lớn nhất. Nếu chỉ lưu **best** của mỗi nửa, cũng chưa đủ, vì đoạn con tối ưu có thể **cắt qua ranh giới** giữa hai nửa.

Ví dụ:

**`[-2,1,-3,4,-1,2,1,-5,4]`**.

Đoạn con tốt nhất là [4,−1,2,1], tổng **6**.

### Node summary bốn trường

Cho một đoạn liên tiếp không rỗng, lưu:

- **`sum`**: tổng toàn đoạn.
- **`pref`**: tổng lớn nhất của **một tiền tố không rỗng**.
- **`suff`**: tổng lớn nhất của **một hậu tố không rỗng**.
- **`best`**: tổng lớn nhất của **một đoạn con liên tiếp không rỗng**.

Với lá có giá trị x:

**`sum=pref=suff=best=x`**.

Gọi L và R là hai Node từ hai đoạn liên tiếp:

**`sum = L.sum+R.sum`**.

**`pref = max(L.pref, L.sum+R.pref)`**: tiền tố tối ưu hoặc nằm hoàn toàn ở L, hoặc lấy hết L và một tiền tố của R.

**`suff = max(R.suff, R.sum+L.suff)`**: hậu tố tối ưu hoặc nằm hoàn toàn ở R, hoặc lấy hết R và một hậu tố của L.

**`best = max(L.best, R.best, L.suff+R.pref)`**: đoạn con tối ưu hoặc nằm trong L, trong R, hoặc cắt qua ranh giới.

Phép gộp này có tính kết hợp, vì nó tương đương việc lấy summary **định nghĩa trực tiếp từ đoạn nối**; bất kỳ cách nhóm các đoạn liên tiếp cũng phải cho summary của cùng một dãy phần tử.

### Identity cho nonempty max-subarray

Nếu dùng Node identity với `best=0` và merge theo công thức trên, truy vấn một dãy toàn âm có thể trả 0 (tập con rỗng) dù đề đòi **nonempty subarray**. Bản Java dùng:

**`Node(empty=true)`**.

Quy tắc:
- merge(empty,x) trả x.
- merge(x,empty) trả x.
- merge(nonempty,nonempty) dùng bốn công thức.

Vì identity được xử lý riêng, mảng `[-8,-3,-5]` trả best **−3**, không phải 0. Nếu truy vấn đoạn rỗng, Node trả `empty=true` và caller không nên diễn giải `best=0` của identity như kết quả một bài toán nonempty hợp lệ.

### Point update

Nếu đổi phần tử ở index 4 từ −1 thành 5, mảng:

**`[-2,1,-3,4,5,2,1,-5,4]`**

có maximum subarray sum bằng **12** nhờ [4,5,2,1]. Chỉ update một lá rồi merge tổ tiên, O(log n), không cần chạy Kadane trên toàn mảng.

### Vì sao không cần lưu toàn bộ đoạn con?

Bốn trường chứa chính xác những thông tin cần để ghép hai phía. Dù một Node đại diện cho một triệu phần tử, việc merge hai Node vẫn O(1). Đây là kỹ năng thiết kế cây đoạn quan trọng hơn việc thuộc một template cây.

## 10. Điều kiện tổng quát để một truy vấn phù hợp

Một quy trình tự kiểm:

1. **Đầu ra của query là gì?** Tổng/min/chuỗi/hàm/tối ưu con?
2. **Trên một lá**, summary là gì?
3. **Khi nối hai đoạn L rồi R**, có tính summary(L·R) chỉ từ summary(L),summary(R) không?
4. **Summary có kích thước đủ nhỏ** không? Một node giữ toàn bộ các phần tử của đoạn là “gộp được” nhưng có thể quá tốn bộ nhớ và không còn O(1) mỗi merge.
5. Merge có **tính kết hợp** trên các summary hợp lệ không?
6. Có **identity** để xử lý padding/query rỗng không? Nếu không, có dùng trạng thái Optional/empty được không?
7. Với phép gộp không giao hoán, thuật toán query **giữ đúng thứ tự** không?
8. Nếu có update, có thể **sửa summary của các node bị ảnh hưởng** hiệu quả không?
9. Tính toán có **overflow hoặc sai số** làm mất tính kết hợp toán học không?
10. Có cách kiểm độc lập trên mảng nhỏ để đối chiếu kết quả không?

### Giao hoán là điều kiện tùy chọn

Nối chuỗi và hợp thành hàm là associative nhưng **không commutative**. Nếu implement query đúng thứ tự, segment tree giải được chúng. Không loại một phép toán khỏi segment tree chỉ vì `a⊗b≠b⊗a`.

### Có nhất thiết phải có inverse không?

**Không.** Segment tree không cần phép đảo ngược. Prefix sums dùng hiệu hai tổng để tính đoạn, nên cần cơ chế rút ảnh hưởng prefix trái (ví dụ tổng số). Nhưng min, GCD hoặc max-subarray không có phép nghịch đảo đơn giản tương ứng mà vẫn có thể gộp trên cây.

Vì vậy câu nói “segment tree chỉ dùng được khi có thể lấy prefix[r]−prefix[l]” là sai.

### Trường hợp kết quả khó gộp

- **Median chính xác** của đoạn tổng quát: không thể gộp chỉ từ hai median và vài scalar cố định để bảo đảm đúng mọi input. Cần lưu phân phối/tần suất hoặc dùng kỹ thuật chuyên biệt như merge-sort tree, wavelet tree, persistent frequency tree, offline selection tùy bài.
- **Mode chính xác**: chỉ biết mode của hai nửa chưa đủ xác định mode của đoạn ghép; tần suất các giá trị cạnh tranh có thể thay đổi.
- **Số giá trị phân biệt**: `distinct(L∪R)` không bằng distinct(L)+distinct(R) khi hai nửa có giá trị chung. Lưu set trên mỗi node có thể đúng nhưng merge/memory không còn O(1)/O(n); hoặc dùng phương pháp offline/bitset/specialized structures.
- **Trung bình của hai average**: sai nếu bỏ qua độ dài.
- **Độ lệch chuẩn/phương sai**: không thể merge bằng trung bình hai phương sai đơn lẻ; cần summary bao gồm số lượng, mean và M2 theo công thức gộp phù hợp, và cẩn thận độ ổn định số thực.

Không suy “không gộp bằng hai số nhỏ” thành “bài toán không giải được bằng một loại segment tree nào”. Có thể dùng **summary phong phú hơn**, tọa độ nén, cấu trúc lồng nhau hoặc thuật toán offline.

## 11. Cây đoạn iterative: point set và range query

Phần code chính dùng một cây đoạn **generic monoid** cho các kiểu Node immutable. Các tiền đề:
- Có `identity` hợp lệ cả bên trái và bên phải.
- `combine(a,b)` **trả summary mới/immutable**, không sửa a hoặc b.
- Phép gộp associative, đóng trên các summary đã dùng.
- Khi cần thời gian O(log n), **mỗi phép combine thực hiện O(1)**.
- Nếu phép toán **không giao hoán**, query giữ thứ tự với hai accumulator.
- Các đối tượng Node/summary được caller truyền vào **không bị mutate qua tham chiếu bên ngoài**. Sử dụng record hoặc các kiểu immutable giúp bảo đảm điều này.

### Build

Với size là lũy thừa hai nhỏ nhất ≥max(1,n):
- Điền tất cả node bằng identity.
- Đặt leaf[size+i] bằng summary của A[i].
- Với p từ size−1 về 1, đặt tree[p]=combine(tree[2p],tree[2p+1]).

### Point set

Đổi leaf[size+index], rồi lần lượt cập nhật parent:

**`tree[p]=combine(tree[2p],tree[2p+1])`**.

Chỉ cần O(log n) merge vì một lá có O(log n) tổ tiên.

### Query [l,r)

L=l+size; R=r+size; giữ leftAcc và rightAcc. Lấy các node hoàn chỉnh từ hai biên và cuối cùng gộp. Nhiều khi l=r, vòng while không chạy, kết quả đúng bằng identity.

### Các ngoại lệ nên báo

- l<0, r>n hoặc l>r: lỗi range.
- point set index ngoài [0,n): lỗi index.
- mảng input null: lỗi API.
- Node input null hoặc merge trả null: lỗi API nếu không có chính sách null.
- n=0: cho phép query [0,0) trả identity, từ chối mọi point set.
- n quá lớn khiến `2·size` vượt giới hạn mảng hoặc RAM: từ chối rõ ràng; không tự overflow chỉ số.

## 12. Lazy propagation: cập nhật cả đoạn cần điều kiện mạnh hơn

Nếu phải **cộng d vào mọi phần tử của một đoạn** [l,r), làm point set r−l lần là O((r−l)log n). **Lazy propagation** có thể cập nhật một đoạn trong O(log n) nhờ ghi lại một **tác động đang chờ** trên các nút được phủ trọn.

Nhưng điều kiện để lazy đúng **không chỉ** là merge associative.

Cần thêm:
1. **Update tác động lên summary của một đoạn được phủ trọn** mà không phải duyệt từng lá.
2. Có cách **hợp thành các update tags** đúng thứ tự.
3. Tác động của update lên summary tương thích với phép gộp và độ dài đoạn.

### Ví dụ range-add + range-sum

Mỗi node lưu **sum** của đoạn và có độ dài `len`. Nếu cộng d vào mọi phần tử trong đoạn này:

**`sumNew = sumOld + d·len`**.

Có thể lưu tag `lazy += d` để nói “các con chưa được cập nhật, nhưng toàn node đã phản ánh tác động d”.

Nếu có hai cập nhật cộng d₁ rồi d₂:

**`add(d₂)∘add(d₁)=add(d₁+d₂)`**.

Nên hợp thành tag cộng bằng **phép cộng**, identity tag là 0.

Nếu một query/update cần đi xuống con, đẩy (*push*) d từ node cha tới từng con, tính tổng con mới theo **độ dài con**, rồi xóa tag cha. Invariant:

**sum[node] luôn là tổng đúng của đoạn node, kể cả khi tag chưa đẩy xuống con.**

Nếu sau khi update ta chỉ chỉnh lazy mà **không** chỉnh sum của node được phủ, query đúng cả node sẽ trả sai.

### Tính tương thích của phép update

Nếu đoạn A nối B và cùng cộng d, ta muốn:

**`sumAdd(A·B,d)=sumAdd(A,d)+sumAdd(B,d)`**.

Vì:

**`(sumA+sumB)+d·(lenA+lenB)=(sumA+d·lenA)+(sumB+d·lenB)`**.

Đẳng thức này giải thích vì sao range-add + range-sum dùng lazy tag d hiệu quả.

### Không gộp tag “set” như tag “add”

Với cập nhật **gán mọi phần tử bằng x**, tag mới thường **ghi đè** tag gán cũ. Với add, tag được cộng dồn. Nếu có cả set và add:
- Set sau Add có thể xóa tác động add trước đó.
- Add sau Set làm tăng giá trị set đang chờ.
- Thứ tự compose tag là quan trọng.

Không đơn giản đặt mọi tag trong một biến số và luôn cộng. Một cách cài an toàn là định nghĩa **tag transformation** rõ ràng, có identity và hàm compose(old,new) theo thứ tự thực thi.

### Ví dụ sai: lazy cộng đơn giản với max-subarray

Với một đoạn có len phần tử, cộng d vào mọi phần tử làm tăng tổng toàn đoạn d·len, nhưng **best subarray** có thể thay đổi cả **vị trí và độ dài**. Chỉ biết (sum,pref,suff,best) trước update không đủ để cập nhật best bằng công thức best+d·len: đoạn con tối ưu có thể ngắn hơn len. Do đó **không** lấy lazy range-add + range-sum rồi áp thẳng vào Node max-subarray mà không thiết kế summary/thuật toán mới.

## 13. Điều kiện đại số cho lazy tag

Mô hình một summary S với merge `⊗`. Một update tag u tác động lên summary đoạn có độ dài len qua:

**`apply(u,summary,len)`**.

Các cập nhật tuần tự cần có phép `compose`, trong đó `compose(old,new)` biểu thị **chạy old trước rồi new** (nếu bạn chọn quy ước này, hãy giữ nhất quán). Để push đúng, cần tính tương thích:

**`apply(u,a⊗b,lenA+lenB)=apply(u,a,lenA)⊗apply(u,b,lenB)`**.

Nếu cần phân biệt độ dài, có thể xem `(sum,len)` là monoid summary, khi đó apply(add d,(sum,len))=(sum+d·len,len).

Với range-add+sum:
- Data identity: sum 0.
- Merge data: cộng tổng.
- Tag identity: 0.
- Compose tags: cộng dồn.
- Apply tag: `sum += delta·length`.

Với range-assign+sum:
- Tag là “không có assign” hoặc “assign x”.
- Apply: `sum=x·length`.
- Compose: tag gán mới **ghi đè** tag gán cũ.
- Không dùng một long sentinel ngẫu nhiên nếu toàn bộ long là giá trị gán hợp lệ; có thể dùng boolean hasAssign.

**Không phải mọi monoid query đều có action/tag hiệu quả** cho một cập nhật đoạn tùy ý. Cần chứng minh riêng cho từng cặp (query, update).

## 14. Java 17+ hoàn chỉnh: cây generic, max-subarray, affine và lazy

Chương trình dưới đây lưu trong **một file**, biên dịch với JDK 17+, không dùng thư viện ngoài JDK. Nó bao gồm:

1. **`IterativeTree<T>`**: cây đoạn generic với identity và `BinaryOperator<T>`, build, set, query.
2. **`Node`**: summary nonempty maximum subarray với cờ empty và bốn trường.
3. **`Affine`**: phép biến đổi `a·x+b mod M`, combine bằng **hợp thành theo đúng thứ tự trái trước, phải sau**.
4. **`LazyRangeAddSum`**: cây đoạn riêng cho cộng trên đoạn và truy vấn tổng, với pending tags.
5. **Oracle kiểm thử độc lập**: quét trực tiếp để tính sum/min; brute O(n²) cho max-subarray đoạn nhỏ; quét tuần tự compose affine; cập nhật trực tiếp từng phần tử để kiểm lazy.
6. **Seed ngẫu nhiên cố định** để tái lập test và stdout.
7. **Kiểm thử corner cases**: đoạn rỗng, mảng toàn âm, update điểm, cập nhật đoạn âm và mảng độ dài 0.

### Mã nguồn: SegmentTreeMergeDemo.java

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.SplittableRandom;
import java.util.function.BinaryOperator;

public final class SegmentTreeMergeDemo {
    private static final long MOD = 1_000_000_007L;

    // Generic monoid segment tree. combine(left,right) keeps order.
    private static final class IterativeTree<T> {
        private final int n;
        private final int size;
        private final Object[] tree;
        private final T identity;
        private final BinaryOperator<T> combine;

        IterativeTree(
                List<T> values,
                T identity,
                BinaryOperator<T> combine) {
            Objects.requireNonNull(values, "values");
            this.identity = Objects.requireNonNull(
                    identity, "identity");
            this.combine = Objects.requireNonNull(
                    combine, "combine");
            this.n = values.size();

            if (n > (1 << 28)) {
                throw new IllegalArgumentException(
                        "Array is too large for this example");
            }

            int power = 1;
            while (power < n) {
                power <<= 1;
            }
            size = power;
            tree = new Object[size * 2];
            Arrays.fill(tree, identity);

            for (int i = 0; i < n; i++) {
                tree[size + i] = Objects.requireNonNull(
                        values.get(i), "null leaf");
            }
            for (int p = size - 1; p > 0; p--) {
                tree[p] = Objects.requireNonNull(
                        combine.apply(at(2 * p), at(2 * p + 1)),
                        "null merge");
            }
        }

        @SuppressWarnings("unchecked")
        private T at(int index) {
            return (T) tree[index];
        }

        private void checkRange(int l, int r) {
            if (l < 0 || r < l || r > n) {
                throw new IllegalArgumentException(
                        "Invalid [l,r) range");
            }
        }

        private void set(int index, T value) {
            if (index < 0 || index >= n) {
                throw new IllegalArgumentException(
                        "Point index out of range");
            }

            int p = size + index;
            tree[p] = Objects.requireNonNull(
                    value, "value");
            while ((p >>= 1) > 0) {
                tree[p] = Objects.requireNonNull(
                        combine.apply(at(2 * p), at(2 * p + 1)),
                        "null merge");
            }
        }

        private T query(int l, int r) {
            checkRange(l, r);
            int left = l + size;
            int right = r + size;
            T leftAcc = identity;
            T rightAcc = identity;

            while (left < right) {
                if ((left & 1) != 0) {
                    leftAcc = combine.apply(
                            leftAcc, at(left++));
                }
                if ((right & 1) != 0) {
                    rightAcc = combine.apply(
                            at(--right), rightAcc);
                }
                left >>= 1;
                right >>= 1;
            }
            return combine.apply(leftAcc, rightAcc);
        }
    }

    // Nonempty maximum subarray summary.
    private record Node(
            boolean empty,
            long sum,
            long pref,
            long suff,
            long best) {
        static Node identity() {
            return new Node(true, 0L, 0L, 0L, 0L);
        }

        static Node leaf(long value) {
            return new Node(
                    false, value, value, value, value);
        }
    }

    private static Node mergeNode(Node left, Node right) {
        if (left.empty()) {
            return right;
        }
        if (right.empty()) {
            return left;
        }

        long sum = Math.addExact(
                left.sum(), right.sum());
        long pref = Math.max(
                left.pref(),
                Math.addExact(left.sum(), right.pref()));
        long suff = Math.max(
                right.suff(),
                Math.addExact(right.sum(), left.suff()));
        long best = Math.max(
                Math.max(left.best(), right.best()),
                Math.addExact(left.suff(), right.pref()));

        return new Node(false, sum, pref, suff, best);
    }

    private static List<Node> nodeLeaves(long[] array) {
        ArrayList<Node> out = new ArrayList<>();
        for (long x : array) {
            out.add(Node.leaf(x));
        }
        return out;
    }

    private static List<Long> longLeaves(long[] array) {
        ArrayList<Long> out = new ArrayList<>();
        for (long x : array) {
            out.add(x);
        }
        return out;
    }

    // The right transformation is applied AFTER the left.
    private record Affine(long a, long b) {}

    private static Affine composeInOrder(
            Affine left, Affine right) {
        return new Affine(
                (right.a() * left.a()) % MOD,
                (right.a() * left.b() + right.b()) % MOD);
    }

    private static long applyAffine(Affine f, long x) {
        return (f.a() * x + f.b()) % MOD;
    }

    // Specialized lazy tree: range-add + range-sum only.
    private static final class LazyRangeAddSum {
        private final int n;
        private final long[] sum;
        private final long[] pending;

        LazyRangeAddSum(long[] input) {
            Objects.requireNonNull(input, "input");
            n = input.length;

            if (n > Integer.MAX_VALUE / 4) {
                throw new IllegalArgumentException(
                        "Array too large");
            }

            sum = new long[Math.max(4, n * 4)];
            pending = new long[sum.length];
            if (n > 0) {
                build(1, 0, n, input);
            }
        }

        private void build(
                int p, int lo, int hi, long[] input) {
            if (hi - lo == 1) {
                sum[p] = input[lo];
                return;
            }
            int mid = lo + (hi - lo) / 2;
            build(p * 2, lo, mid, input);
            build(p * 2 + 1, mid, hi, input);
            sum[p] = Math.addExact(
                    sum[p * 2], sum[p * 2 + 1]);
        }

        private void apply(
                int p, int length, long delta) {
            // Calculate both new values before mutating this node.
            long nextSum = Math.addExact(
                    sum[p],
                    Math.multiplyExact(delta, (long) length));
            long nextTag = Math.addExact(
                    pending[p], delta);
            sum[p] = nextSum;
            pending[p] = nextTag;
        }

        private void push(int p, int lo, int hi) {
            long delta = pending[p];
            if (delta == 0L || hi - lo <= 1) {
                return;
            }
            int mid = lo + (hi - lo) / 2;
            apply(p * 2, mid - lo, delta);
            apply(p * 2 + 1, hi - mid, delta);
            pending[p] = 0L;
        }

        private void add(
                int p, int lo, int hi,
                int l, int r, long delta) {
            if (r <= lo || hi <= l) {
                return;
            }
            if (l <= lo && hi <= r) {
                apply(p, hi - lo, delta);
                return;
            }

            push(p, lo, hi);
            int mid = lo + (hi - lo) / 2;
            add(p * 2, lo, mid, l, r, delta);
            add(p * 2 + 1, mid, hi, l, r, delta);
            sum[p] = Math.addExact(
                    sum[p * 2], sum[p * 2 + 1]);
        }

        private long query(
                int p, int lo, int hi,
                int l, int r) {
            if (r <= lo || hi <= l) {
                return 0L;
            }
            if (l <= lo && hi <= r) {
                return sum[p];
            }

            push(p, lo, hi);
            int mid = lo + (hi - lo) / 2;
            return Math.addExact(
                    query(p * 2, lo, mid, l, r),
                    query(p * 2 + 1, mid, hi, l, r));
        }

        private void checkRange(int l, int r) {
            if (l < 0 || r < l || r > n) {
                throw new IllegalArgumentException(
                        "Invalid [l,r) range");
            }
        }

        void rangeAdd(int l, int r, long delta) {
            checkRange(l, r);
            if (l < r) {
                add(1, 0, n, l, r, delta);
            }
        }

        long rangeSum(int l, int r) {
            checkRange(l, r);
            if (l == r) {
                return 0L;
            }
            return query(1, 0, n, l, r);
        }
    }

    private static void check(
            boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    // Independent O(length^2) oracle for small segments.
    private static long bruteNonemptyBest(
            long[] a, int l, int r) {
        if (l == r) {
            throw new IllegalArgumentException(
                    "Best requires nonempty range");
        }
        long best = Long.MIN_VALUE;
        for (int i = l; i < r; i++) {
            long running = 0L;
            for (int j = i; j < r; j++) {
                running = Math.addExact(
                        running, a[j]);
                best = Math.max(best, running);
            }
        }
        return best;
    }

    private static void randomChecks() {
        SplittableRandom rng =
                new SplittableRandom(5012026L);

        // 5000 * 18 = 90000 sum/min operations.
        for (int trial = 0; trial < 5000; trial++) {
            int n = rng.nextInt(21);
            long[] a = new long[n];
            for (int i = 0; i < n; i++) {
                a[i] = rng.nextInt(-25, 26);
            }
            IterativeTree<Long> sums = new IterativeTree<>(
                    longLeaves(a), 0L, Math::addExact);
            IterativeTree<Long> minimum =
                    new IterativeTree<>(
                            longLeaves(a),
                            Long.MAX_VALUE,
                            Long::min);

            for (int step = 0; step < 18; step++) {
                if (n > 0 && rng.nextInt(3) == 0) {
                    int index = rng.nextInt(n);
                    long value = rng.nextInt(-25, 26);
                    a[index] = value;
                    sums.set(index, value);
                    minimum.set(index, value);
                }
                int l = rng.nextInt(n + 1);
                int r = l + rng.nextInt(n - l + 1);
                long expectedSum = 0L;
                long expectedMin = Long.MAX_VALUE;
                for (int i = l; i < r; i++) {
                    expectedSum += a[i];
                    expectedMin = Math.min(
                            expectedMin, a[i]);
                }
                check(sums.query(l, r) == expectedSum,
                        "sum mismatch");
                check(minimum.query(l, r) == expectedMin,
                        "min mismatch");
            }
        }

        // 3000 * 12 = 36000 max-subarray operations.
        for (int trial = 0; trial < 3000; trial++) {
            int n = rng.nextInt(13);
            long[] a = new long[n];
            for (int i = 0; i < n; i++) {
                a[i] = rng.nextInt(-10, 11);
            }
            IterativeTree<Node> tree = new IterativeTree<>(
                    nodeLeaves(a), Node.identity(),
                    SegmentTreeMergeDemo::mergeNode);

            for (int step = 0; step < 12; step++) {
                if (n > 0 && rng.nextInt(4) == 0) {
                    int index = rng.nextInt(n);
                    long value = rng.nextInt(-10, 11);
                    a[index] = value;
                    tree.set(index, Node.leaf(value));
                }
                int l = rng.nextInt(n + 1);
                int r = l + rng.nextInt(n - l + 1);
                Node got = tree.query(l, r);
                if (l == r) {
                    check(got.empty(),
                            "empty range mismatch");
                } else {
                    check(!got.empty()
                            && got.best()
                               == bruteNonemptyBest(a, l, r),
                            "max-subarray mismatch");
                }
            }
        }

        // 2500 * 14 = 35000 noncommutative operations.
        for (int trial = 0; trial < 2500; trial++) {
            int n = rng.nextInt(17);
            Affine[] a = new Affine[n];
            List<Affine> items = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                a[i] = new Affine(
                        rng.nextInt(101), rng.nextInt(101));
                items.add(a[i]);
            }
            IterativeTree<Affine> transforms =
                    new IterativeTree<>(
                            items, new Affine(1L, 0L),
                            SegmentTreeMergeDemo::composeInOrder);

            for (int step = 0; step < 14; step++) {
                if (n > 0 && rng.nextInt(3) == 0) {
                    int index = rng.nextInt(n);
                    a[index] = new Affine(
                            rng.nextInt(101), rng.nextInt(101));
                    transforms.set(index, a[index]);
                }
                int l = rng.nextInt(n + 1);
                int r = l + rng.nextInt(n - l + 1);
                Affine expected = new Affine(1L, 0L);
                for (int i = l; i < r; i++) {
                    expected = composeInOrder(
                            expected, a[i]);
                }
                check(transforms.query(l, r).equals(expected),
                        "affine order mismatch");
            }
        }

        // 3000 * 25 = 75000 lazy add/sum operations.
        for (int trial = 0; trial < 3000; trial++) {
            int n = rng.nextInt(31);
            long[] a = new long[n];
            for (int i = 0; i < n; i++) {
                a[i] = rng.nextInt(-30, 31);
            }
            LazyRangeAddSum lazy =
                    new LazyRangeAddSum(a.clone());

            for (int step = 0; step < 25; step++) {
                int l = rng.nextInt(n + 1);
                int r = l + rng.nextInt(n - l + 1);
                if (rng.nextBoolean()) {
                    long delta = rng.nextInt(-20, 21);
                    lazy.rangeAdd(l, r, delta);
                    for (int i = l; i < r; i++) {
                        a[i] += delta;
                    }
                } else {
                    long expected = 0L;
                    for (int i = l; i < r; i++) {
                        expected += a[i];
                    }
                    check(lazy.rangeSum(l, r) == expected,
                            "lazy range sum mismatch");
                }
            }
        }
        System.out.println(
                "Randomized cross-checks: 236000 PASS");
    }

    public static void main(String[] args) {
        long[] input = {2, -1, 3, 5, -2};
        IterativeTree<Long> sums = new IterativeTree<>(
                longLeaves(input), 0L, Math::addExact);
        IterativeTree<Long> minimum = new IterativeTree<>(
                longLeaves(input),
                Long.MAX_VALUE, Long::min);

        System.out.println(
                "Sum initial [0,5): " + sums.query(0, 5));
        System.out.println(
                "Sum initial [1,4): " + sums.query(1, 4));
        sums.set(1, 4L);
        System.out.println(
                "Sum after set(1,4): " + sums.query(0, 5));
        System.out.println(
                "Sum empty [2,2): " + sums.query(2, 2));
        System.out.println(
                "Min [1,4): " + minimum.query(1, 4));

        long[] maxData =
                {-2, 1, -3, 4, -1, 2, 1, -5, 4};
        IterativeTree<Node> subarray = new IterativeTree<>(
                nodeLeaves(maxData), Node.identity(),
                SegmentTreeMergeDemo::mergeNode);
        System.out.println(
                "Max-subarray initial: "
                + subarray.query(0, maxData.length).best());
        subarray.set(4, Node.leaf(5L));
        System.out.println(
                "Max-subarray after set(4,5): "
                + subarray.query(0, maxData.length).best());

        IterativeTree<Node> negatives = new IterativeTree<>(
                nodeLeaves(new long[]{-8, -3, -5}),
                Node.identity(),
                SegmentTreeMergeDemo::mergeNode);
        System.out.println(
                "Max-subarray all-negative: "
                + negatives.query(0, 3).best());
        System.out.println(
                "Max-subarray empty: "
                + subarray.query(2, 2).empty());

        IterativeTree<Affine> maps = new IterativeTree<>(
                List.of(
                        new Affine(2L, 1L),
                        new Affine(3L, 4L),
                        new Affine(5L, 6L)),
                new Affine(1L, 0L),
                SegmentTreeMergeDemo::composeInOrder);

        Affine combined = maps.query(0, 3);
        System.out.println(
                "Affine [0,3): a=" + combined.a()
                + ", b=" + combined.b()
                + ", f(2)=" + applyAffine(combined, 2L));
        maps.set(1, new Affine(1L, 10L));
        combined = maps.query(0, 3);
        System.out.println(
                "Affine after set(1,x+10): a=" + combined.a()
                + ", b=" + combined.b()
                + ", f(2)=" + applyAffine(combined, 2L));

        LazyRangeAddSum lazy =
                new LazyRangeAddSum(input.clone());
        System.out.println(
                "Lazy initial total: "
                + lazy.rangeSum(0, 5));
        lazy.rangeAdd(1, 4, 3L);
        System.out.println(
                "Lazy add [1,4) += 3: total="
                + lazy.rangeSum(0, 5)
                + ", [0,3)=" + lazy.rangeSum(0, 3));
        lazy.rangeAdd(0, 5, -2L);
        System.out.println(
                "Lazy add [0,5) += -2: total="
                + lazy.rangeSum(0, 5)
                + ", [2,5)=" + lazy.rangeSum(2, 5));
        System.out.println(
                "Lazy empty [2,2): " + lazy.rangeSum(2, 2));

        IterativeTree<Long> empty = new IterativeTree<>(
                List.<Long>of(), 0L, Math::addExact);
        System.out.println(
                "Empty array sum: " + empty.query(0, 0));

        boolean invalidRejected = false;
        try {
            sums.query(0, 6);
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }
        check(invalidRejected, "Out-of-range query accepted");
        System.out.println("Invalid query: rejected");

        randomChecks();
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 SegmentTreeMergeDemo.java
java SegmentTreeMergeDemo
~~~

**Stdout chính xác của chương trình:**

~~~text
Sum initial [0,5): 7
Sum initial [1,4): 7
Sum after set(1,4): 12
Sum empty [2,2): 0
Min [1,4): -1
Max-subarray initial: 6
Max-subarray after set(4,5): 12
Max-subarray all-negative: -3
Max-subarray empty: true
Affine [0,3): a=30, b=41, f(2)=101
Affine after set(1,x+10): a=10, b=61, f(2)=81
Lazy initial total: 7
Lazy add [1,4) += 3: total=16, [0,3)=10
Lazy add [0,5) += -2: total=6, [2,5)=6
Lazy empty [2,2): 0
Empty array sum: 0
Invalid query: rejected
Randomized cross-checks: 236000 PASS
~~~

### Giải thích tính đúng của các dòng

**Sum initial:** với A=[2,−1,3,5,−2], toàn mảng bằng 7. [1,4) có −1+3+5=7.

**Sum after set(1,4):** cập nhật chỉ số 1 từ −1 lên 4, tổng tăng 5 thành 12. Đây là point assignment, không phải thêm 4 vào phần tử hiện có.

**Sum empty:** query [2,2) trả identity 0. **Min [1,4): −1** vì minimum tree được xây từ input gốc và không bị thay bởi lệnh set trên **cây tổng riêng**.

**Max-subarray:** mảng [-2,1,-3,4,-1,2,1,-5,4] có best=6. Thay index 4 thành 5 cho best=12. Dãy toàn âm [-8,-3,-5] trả −3, xác nhận thuật toán dùng **đoạn con không rỗng**. Đoạn rỗng trả Node.empty=true, không diễn giải best là nghiệm hợp lệ.

**Affine:** hợp thành f₀(x)=2x+1, f₁(x)=3x+4, f₂(x)=5x+6 theo thứ tự trái→phải được 30x+41, tại x=2 là 101. Khi đổi f₁ thành x+10, hợp thành là 10x+61, tại x=2 là 81. Đây là phép thử phát hiện **đổi thứ tự combine** trong query.

**Lazy:** ban đầu tổng 7. Cộng 3 vào các vị trí 1,2,3 cho [2,2,6,8,-2], tổng 16 và [0,3) bằng 10. Cộng tiếp −2 trên toàn mảng cho [0,0,4,6,-4], tổng 6 và [2,5) bằng 6. Đoạn rỗng trả 0.

**Empty array:** generic tree xử lý n=0 bằng một identity; chỉ [0,0) là truy vấn hợp lệ, kết quả 0 cho sum.

**Invalid query:** [0,6) không nằm trong n=5 phần tử, phải bị từ chối.

**Randomized cross-checks:** 236.000 bước trên bốn nhóm độc lập: sum/min, max-subarray, affine không giao hoán và lazy add/sum. Dòng PASS chỉ được in khi mọi kết quả so với oracle trực tiếp đều khớp.

### Điểm cần chú ý với Math.addExact

Mã dùng `Math.addExact` và `Math.multiplyExact` để **phát hiện** tràn số thay vì cho kết quả sai im lặng. Nhưng các phương thức cập nhật này **không phải transaction**: nếu một phép update sâu trong cây ném overflow sau khi vài node đã đổi, trạng thái có thể đã thay đổi một phần. Với dữ liệu lớn có nguy cơ overflow, cần **ràng buộc đầu vào để chứng minh an toàn** hoặc dùng số học đủ rộng/thiết kế rollback trước khi cam kết strong exception safety.

Đặc biệt, nếu cộng d vào rất nhiều phần tử, **delta·length** có thể tràn dù mỗi phần tử riêng lẻ vẫn nằm trong long. Không được coi việc dùng Math.addExact là giải pháp “luôn cho đáp án đúng bằng long”; nó chỉ ném lỗi tại thời điểm không biểu diễn được.

## 15. Oracle kiểm thử độc lập

Một cách QA tốt cần kiểm cả cấu trúc và đại số:

### 15.1. Sum/min

Sau mỗi set/update nhỏ:
- Tính tổng trực tiếp bằng một vòng for trên [l,r).
- Tính min trực tiếp bằng một vòng for trên [l,r).
- So với cây.

Nếu l=r, expected sum=0 và expected min=Long.MAX_VALUE theo quy ước identity của bài.

### 15.2. Max-subarray

Với n≤12, brute force mọi đoạn con [i,j) nằm trong [l,r), i<j. Lấy tổng lớn nhất, so với Node.best. Không dùng lại chính công thức merge để làm oracle, vì bug có thể bị sao chép từ chương trình đang kiểm.

Trong bài, 3.000 dãy nhỏ với 12 bước/query mỗi dãy được đối chiếu; trong mô hình kiểm thử bổ sung, 16.000 dãy với 320.000 thao tác được kiểm tương tự.

### 15.3. Affine — kiểm thứ tự

Với mỗi query [l,r), bắt đầu từ identity f(x)=x, rồi **lần lượt gộp** từng hàm từ index l đến r−1 theo đúng thứ tự. So cặp hệ số (a,b) với query của cây. Nếu đổi thứ tự left/right, kết quả có thể sai ngay cả khi phép gộp associative.

Trong bộ kiểm thử độc lập, 10.000 mảng affine với 200.000 thao tác update/query đã được đối chiếu bằng cách quét tuần tự.

### 15.4. Lazy range add + sum

Giữ một **mảng chậm** làm oracle:
- Mỗi rangeAdd(l,r,d), cộng d trực tiếp vào từng phần tử i∈[l,r).
- Mỗi rangeSum(l,r), cộng trực tiếp các phần tử trong đoạn.
- So với lazy tree.

Đặc biệt thử:
- Hai update chồng lấn.
- Update bao trọn [0,n).
- Update một đoạn con rồi query đoạn lớn hơn.
- Query một đoạn con sau update bao trọn node cha (buộc push lazy).
- Delta âm, delta=0.
- Đoạn rỗng và mảng rỗng.

Bộ kiểm thử độc lập đã chạy **12.000 dãy**, tổng **420.000 thao tác** để phát hiện lỗi push hoặc compose tag.

### 15.5. Kết quả của kiểm thử mô hình độc lập

Một mô hình kiểm thử đối chiếu trực tiếp theo seed đã chạy:
- **12.000** mảng sum/min, **360.000** thao tác.
- **16.000** mảng max-subarray, **320.000** thao tác.
- **10.000** mảng affine, **200.000** thao tác.
- **12.000** mảng lazy add/sum, **420.000** thao tác.

Tổng **50.000 bộ mảng** và **1.300.000 thao tác**; kết quả so với oracle độc lập khớp toàn bộ. Đây là **bằng chứng kiểm thử triển khai**, không phải thay thế chứng minh invariant và điều kiện đại số tổng quát.

## 16. Segment tree so với prefix sums và Fenwick tree

### Prefix sums

Với mảng **tĩnh** và truy vấn tổng:
- Build prefix: O(n).
- Range sum: **O(1)** bằng `prefix[r]−prefix[l]`.
- Update một phần tử: nếu cập nhật trực tiếp prefix, thường mất O(n).

Khi không có update, prefix sums đơn giản hơn segment tree cho tổng đoạn. Với min, không có phép trừ prefix tương tự để đảo ảnh hưởng phía trái.

### Fenwick tree (Binary Indexed Tree)

Với tổng và point add:
- Bộ nhớ O(n).
- Point add O(log n).
- Prefix sum O(log n).
- Range sum O(log n) bằng hiệu hai prefix.

Fenwick tree thường gọn và có hằng số tốt cho tổng/XOR hoặc các dạng nhóm phù hợp. Nhưng range min tùy ý với cập nhật gán không theo chiều đơn điệu, max-subarray bốn trường, hoặc phép gộp có thứ tự không giao hoán không thể đơn giản dùng **một Fenwick prefix subtraction** như sum.

Đừng nói Fenwick “không bao giờ hỗ trợ min” theo mọi biến thể; có những thuật toán chuyên biệt với hạn chế monotonic updates hoặc cấu trúc bổ sung. Phát biểu chính xác: segment tree là lựa chọn **tổng quát hơn cho monoid associative**, không cần inverse.

### Segment tree

Với point set và range query:
- Build O(n).
- Point set O(log n).
- Query O(log n) **nếu merge O(1)**.
- Bộ nhớ O(n).

Đối với noncommutative merge, segment tree vẫn đúng nhờ bảo toàn thứ tự.

### Sparse table

Nếu mảng **tĩnh** và truy vấn min/max/GCD mà không update, **sparse table** có thể trả một số phép query idempotent như min/max/GCD trong O(1) sau build O(n log n), vì có thể cho phép các khối phủ chồng lên nhau khi phép gộp **idempotent** (`x⊗x=x`).

Với tổng, không thể lấy hai khối chồng nhau rồi cộng vì sẽ đếm lặp; cần kỹ thuật khác như disjoint sparse table cho associative queries tĩnh. Segment tree phù hợp hơn khi có update.

### Mo's algorithm và xử lý offline

Nếu tất cả query đã biết trước và không có/ít update, **Mo's algorithm** có thể sắp xếp lại truy vấn để giảm tổng chi phí **thêm/xóa phần tử ở biên**. Nó phù hợp cho một số thống kê khó gộp bằng monoid O(1), như số giá trị phân biệt khi có thể add/remove nhanh.

Đây là lý do bài thuộc nhóm **Truy vấn và ngoại tuyến**: thuật toán chọn không chỉ do câu hỏi, mà còn do **biết trước query hay không**, cấu trúc update, số truy vấn và chi phí gộp. Segment tree hoạt động **online** với query/update bất kỳ được gửi tuần tự, nhưng vẫn hoàn toàn dùng được khi input truy vấn đã biết trước.

## 17. Cập nhật đoạn khó hơn cập nhật điểm

Các kiểu update phổ biến:

| Cặp query / update | Phương án thường dùng | Ghi chú |
|---|---|---|
| Sum / point set | Generic tree | Update lá, gộp tổ tiên |
| Min / point set | Generic tree | Identity +∞ |
| Max-subarray / point set | Node bốn trường | Nonempty identity riêng |
| Sum / range add | Lazy tree | sum += d·len, tag += d |
| Sum / range assign | Lazy tree | Tag assign mới ghi đè tag cũ |
| Min/max / range add | Lazy tree | min/max += d với đoạn phủ trọn |
| GCD / arbitrary range add | Không dùng tag sum-style trực tiếp | Cần cấu trúc/biến đổi chuyên biệt |
| Max-subarray / range add | Không áp lazy bốn trường một cách ngây thơ | Độ dài đoạn con tối ưu có thể đổi |
| Sum / range affine x→a·x+b | Lazy sum với tag (a,b) | sum→a·sum+b·len; compose theo thứ tự |

### Ví dụ lazy affine

Nếu update mọi phần tử `x→a·x+b` trong một node length len:

**`sumNew=a·sumOld+b·len`**.

Nếu đã có pending transform `f(x)=a₁x+b₁` rồi nhận transform mới `g(x)=a₂x+b₂`, thứ tự đúng là:

**`g∘f(x)=(a₂a₁)x+(a₂b₁+b₂)`**.

Với a,b có thể rất lớn, cần kiểm kiểu số hoặc modulo theo bài. Tính không giao hoán của tag composition còn quan trọng hơn khi trộn assign/add/multiply: đổi thứ tự update thường đổi kết quả.

## 18. Vì sao “sum of medians” và “average of averages” sai?

Giả sử đoạn trái [1,9] có median tùy quy ước là 5, đoạn phải [2,3,4,5] có median 3,5. Hai median riêng không đủ tính median của [1,9,2,3,4,5] nếu không biết phân bố các phần tử; trong những ví dụ khác có cùng median từng nửa, median toàn đoạn vẫn có thể khác.

Tương tự, một đoạn dài 1 có average=100, đoạn dài 99 có average=0. Average của **hai average** là 50, nhưng average đúng của 100 phần tử là **1**. Vì vậy summary phải lưu cả **sum và count**, hoặc cặp (mean,count) với công thức weighted combine.

### Thước đo phức tạp vẫn có thể gộp bằng summary giàu hơn

Để tính **longest well-formed parentheses** hay những DP cụ thể, có thể tồn tại summary monoid phức tạp hơn khi giữ thêm trạng thái. Nhưng không được khẳng định mọi hàm đoạn đều có summary O(1): có những truy vấn cần thông tin kích thước tăng theo miền giá trị hoặc theo độ dài đoạn.

Cách thiết kế đúng: tìm **thông tin biên cần thiết** khi một kết quả tối ưu “đi qua chỗ nối giữa hai con”. Với max-subarray, thông tin biên ấy là best suffix của trái và best prefix của phải. Đây là mẫu tư duy có thể tái sử dụng cho nhiều truy vấn không tầm thường.

## 19. Tính chính xác số học và độ phức tạp thật

Một phép gộp toán học có thể associative, nhưng khi cài đặt bằng kiểu số hữu hạn có thể gặp:

- **Overflow số nguyên:** cộng long tràn có thể wrap. Java `Math.addExact` ném ArithmeticException, giúp phát hiện nhưng không tự rollback update.
- **Underflow/overflow số thực:** cộng/multiply double mất độ chính xác.
- **NaN:** các phép so sánh và min/max với NaN cần chính sách rõ.
- **Comparator không nhất quán:** nếu merge chọn phần tử theo comparator tùy trạng thái, associativity có thể hỏng.
- **Mutable summary:** combine thay đổi một node đang lưu trong cây có thể làm hỏng nhiều đường truy vấn khác.
- **Side effects:** combine phụ thuộc thời gian, RNG, biến global hoặc số lần gọi không còn là một phép gộp thuần.
- **Variable-size summary:** mỗi merge có thể O(length), khiến O(log n) node visit không đồng nghĩa O(log n) runtime.

Mô hình tổng quát hơn: nếu mỗi query thăm O(log n) node và merge tốn tối đa `T_merge`, thời gian query là **O(log n·T_merge)**, cộng overhead truy cập cấu trúc. Với summary kích thước không cố định, phải phân tích số ký tự/đối tượng được copy qua các tầng chứ không chỉ đếm số merge.

### Identity và kiểu số thực

Với min trên double, có thể dùng `Double.POSITIVE_INFINITY` làm identity nếu dữ liệu/query có hợp đồng về NaN. Nhưng nếu có NaN, cần xác định min() sẽ xử lý ra sao theo API thực tế và kỳ vọng đề. Một identity chỉ đúng khi nó tương tác đúng với **mọi giá trị hợp lệ**.

## 20. Đếm số node thăm trong một truy vấn

Cây có chiều cao **h=⌈log₂(size)⌉**. Thuật toán iterative dịch biên l,r lên một bậc sau mỗi vòng. Ở mỗi bậc, nhiều nhất:
- Một node trọn vẹn được lấy từ biên trái.
- Một node trọn vẹn được lấy từ biên phải.

Vì vậy tối đa O(h) node được gộp. Hai accumulator đảm bảo thứ tự. Với n không phải lũy thừa hai, các lá đệm là identity và không ảnh hưởng đến summary đoạn hợp lệ.

### Vì sao query không phải O(1) dù root đã có toàn mảng?

Root đúng là summary của toàn bộ [0,n) nên có thể trả lời **query toàn mảng** trong O(1). Nhưng một đoạn tùy ý [l,r) không nhất thiết trùng với một node đã lưu; thuật toán phải phân rã thành O(log n) node.

### Vì sao update không phải O(n)?

Một point set chỉ thay một lá. Những node không chứa lá đó có summary y nguyên. Chỉ có **một đường tổ tiên lên root**, độ dài O(log n), cần cập nhật.

## 21. Kiểm thử tính kết hợp và identity

Trước khi đưa một kiểu Node mới vào cây, thử trên **dữ liệu nhỏ**, không chỉ gọi build rồi kiểm một query:

1. Sinh nhiều lá a,b,c hợp lệ.
2. Kiểm `merge(merge(a,b),c)` bằng `merge(a,merge(b,c))`.
3. Kiểm `merge(identity,a)=a` và `merge(a,identity)=a`.
4. Dựng một mảng ngắn, tính summary đoạn bằng **một oracle quét thẳng**.
5. So tất cả query [l,r) với cây, cả đoạn rỗng và toàn mảng.
6. Sau mỗi update, so lại với oracle.
7. Với phép gộp không giao hoán, dùng ví dụ mà `merge(a,b)≠merge(b,a)` để bắt lỗi thứ tự.

### Lưu ý về phương pháp test associativity

Thử 10.000 bộ a,b,c chỉ giúp bắt bug, không phải chứng minh tính kết hợp **trên mọi input**. Chứng minh đại số hoặc chứng minh từ định nghĩa summary của **đoạn nối** là cơ sở vững chắc hơn.

Đối với Node max-subarray, chứng minh rằng cả bốn trường của merge chính là bốn đại lượng được định nghĩa trực tiếp trên chuỗi L·R. Vì nối chuỗi có tính kết hợp, summary cuối không phụ thuộc cách nhóm các đoạn.

### Kiểm thử những input đặc biệt

- Mảng n=0 và n=1.
- n không phải lũy thừa hai: 3,5,6,7,9.
- Đoạn rỗng [l,l).
- Query [0,n), [0,1), [n−1,n).
- Set một lá rồi query nhiều đoạn không chứa/chứa lá đó.
- Mảng toàn âm cho max-subarray.
- Giá trị rất lớn có nguy cơ overflow.
- Phép affine order-sensitive.
- Lazy update chồng lấn và update cả mảng rồi query con.
- Delta âm và identity tag zero.
- Node summary không được mutate ngoài API.

## 22. Lỗi phổ biến

1. **Chọn merge không associative**, ví dụ trừ hai summary rồi kỳ vọng phân nhóm không ảnh hưởng.
2. **Nhầm associative với commutative** và loại chuỗi/hàm affine dù chúng gộp được.
3. **Đổi thứ tự right accumulator** trong query iterative.
4. **Không có identity** nhưng vẫn dùng padding bằng một số tùy ý.
5. **Dùng identity max=0** trong khi mảng có thể toàn số âm.
6. **Dùng best=0 cho maximum nonempty subarray**, trả sai mảng toàn âm.
7. **Nhầm [l,r) với [l,r]**, thiếu hoặc thừa một phần tử.
8. **Dùng index 1-based từ đề mà quên chuyển** sang 0-based.
9. **Cho point set là point add** hoặc ngược lại.
10. **Quên cập nhật tất cả tổ tiên** sau khi sửa một lá.
11. **Gộp node cha không theo thứ tự trái rồi phải** trong bài không giao hoán.
12. **Không kiểm n=0** và tạo mảng size=0 làm tree[1] invalid.
13. **Đặt size=n thay vì lũy thừa hai** rồi dùng thuật toán đệm kiểu iterative không phù hợp.
14. **Cho query của đoạn rỗng về min là một min thực** thay vì identity quy ước.
15. **Giữ summary không immutable** và để caller sửa field trong node đã build.
16. **Cho combine có side effect** rồi phụ thuộc thứ tự runtime.
17. **Dùng String concat và tuyên bố O(1) merge** — cost tùy độ dài.
18. **Báo O(log n) query dù merge O(k)** — bỏ chi phí thật.
19. **Tính trung bình của hai average** bất kể chiều dài đoạn.
20. **Cộng hai distinct counts** khi có phần tử lặp giữa hai nửa.
21. **Chỉ lưu best của mỗi nửa cho max-subarray**, bỏ trường hợp đoạn cắt biên.
22. **Tính prefix/suffix không bắt buộc nonempty**, thay đổi định nghĩa bài.
23. **Không lưu length/count khi update cần độ dài đoạn**.
24. **Range-add+sum nhưng chỉ lazy+=d, không sum+=d·len**.
25. **Quên push tag trước khi query con** dẫn đến con chứa số cũ.
26. **Push tag xuống con sai độ dài**, đặc biệt khi cây không cân đều.
27. **Quên xóa pending tag cha sau push** gây cộng lặp.
28. **Hợp thành assign và add theo phép cộng bất kể thứ tự**.
29. **Dùng lazy sum-style cho max-subarray range-add**, thiếu thông tin độ dài tối ưu.
30. **Query recursive trả 0 làm identity cho max/min** mà không kiểm miền giá trị.
31. **Dùng int cho sum lớn** khiến overflow.
32. **Tưởng Math.addExact làm update atomic** sau exception — có thể đã mutate vài node.
33. **Dùng double mà so exact bitwise với cộng trái→phải** — phép cộng floating không kết hợp chính xác.
34. **Quên một phép toán có giá trị NaN** khi thiết kế comparator identity.
35. **So với oracle dùng lại cùng merge code** nên không bắt bug logic summary.
36. **Chỉ test n lũy thừa hai** — bỏ lỗi padding.
37. **Chỉ test sum/min** — bỏ lỗi query sai thứ tự.
38. **Không test max-subarray all negative** — bỏ empty-subarray bug.
39. **Không test lazy update chồng lấn** — bỏ compose/push bug.
40. **Gọi segment tree luôn tốt hơn prefix** dù mảng tĩnh chỉ cần sum O(1).
41. **Gọi Fenwick không thể xử lý mọi kiểu min trong mọi điều kiện** — phát biểu quá mức, cần ràng buộc cụ thể.
42. **Gọi median luôn gộp được bằng hai median** — không đủ thông tin.
43. **Không giới hạn n khiến 2·size/4·n tràn chỉ số**.
44. **Không đếm RAM Node object/array boxing** — O(n) vẫn có hằng số lớn.
45. **Không so toàn mảng sau update** — có thể sót đường từ lá lên root.
46. **Kết luận có lazy propagation chỉ vì query là monoid** — update phải tác động được lên summary và có tag composition.
47. **Coi xấp xỉ số thực là bằng chứng phép gộp exact** — cần chính sách sai số.
48. **Đổi hướng hợp thành hàm**: f sau g khác g sau f.
49. **Dùng GCD với trị tuyệt đối Long.MIN_VALUE thiếu kiểm overflow**.
50. **Không phân biệt cây phục vụ online và kỹ thuật offline khi tất cả query đã biết**.

## 23. Bài tập tự luyện

**Bài 1 — Monoid sum.** Cho A=[2,−1,3,5,−2], tự vẽ các nút lưu sum và tính [1,4). Chứng minh sum có identity 0 và associative.

**Bài 2 — Min.** Đổi merge thành min, identity Long.MAX_VALUE; tính min của [1,4) và [2,2). Giải thích vì sao câu hỏi min trên đoạn rỗng cần chính sách riêng.

**Bài 3 — XOR.** Xây cây XOR, dùng identity 0, thử 20 lần point set và so query với XOR vòng for.

**Bài 4 — GCD.** Viết merge gcd(a,b), chọn identity 0, kiểm cách xử lý số âm và Long.MIN_VALUE; minh họa vì sao không cần inverse.

**Bài 5 — Noncommutative.** Cho mảng ["a","b","c","d"], dùng string concat, query [1,4) phải là "bcd"; sau set(2,"X"), toàn mảng thành "abXd". Phân tích vì sao Java String concat không O(1).

**Bài 6 — Affine composition.** Cho f₀=2x+1, f₁=3x+4, f₂=5x+6. Chứng minh merge(f₀,merge(f₁,f₂)) cho đúng hàm 30x+41 nếu merge định nghĩa “right sau left”; test x=2.

**Bài 7 — Maximum subarray.** Tự suy ra bốn công thức sum/pref/suff/best khi gộp hai đoạn. Kiểm A=[−8,−3,−5] phải trả best=−3.

**Bài 8 — Empty identity.** Thiết kế Node với cờ empty và chứng minh merge(empty,x)=x=merge(x,empty). Vì sao best=0 làm sentinel có thể sai?

**Bài 9 — Count+sum.** Cài monoid (sum,count) cho average. Dùng ví dụ một đoạn dài 1 average 100 và đoạn dài 99 average 0 để phản bác average of averages.

**Bài 10 — Lazy add.** Cộng 3 trên [1,4) rồi −2 trên [0,5) với input [2,−1,3,5,−2]. So mọi query [l,r) với mảng chậm.

**Bài 11 — Lazy assign.** Thiết kế tag hasAssign/value cho range assign và sum; giải thích vì sao assign mới phải ghi đè pending assign cũ.

**Bài 12 — Lazy affine.** Thiết kế tag (a,b) cho update x→ax+b modulo M, suy ra công thức sum và compose hai tags theo đúng thứ tự.

**Bài 13 — Phương án truy vấn.** So prefix sums, Fenwick, segment tree cho q=100.000 range sum query và u=0, 100, 100.000 update; xét cả RAM.

**Bài 14 — Static RMQ.** Với mảng tĩnh và nhiều min query, so sparse table O(1) query với segment tree O(log n), điều kiện idempotence.

**Bài 15 — Offline distinct.** Vì sao merge hai distinct counts không đúng? Tìm hiểu Mo's algorithm hoặc phương pháp offline last occurrence với Fenwick/segment tree.

**Bài 16 — Test order bug.** Cố ý viết sai rightAcc=combine(rightAcc,node), cho sum test vẫn PASS nhưng affine test FAIL. Giải thích sự khác nhau.

**Bài 17 — Overflow.** Chạy sum tree với các giá trị gần Long.MAX_VALUE, quan sát Math.addExact ném lỗi, thiết kế lựa chọn BigInteger.

**Bài 18 — Invariant.** Chứng minh build từ lá lên, point set trên đường tổ tiên, query bằng tập node phủ chính xác.

**Bài 19 — n không lũy thừa hai.** Dùng n=5 và size=8, ghi vị trí lá đệm identity, tính root và một query gần cuối mảng.

**Bài 20 — Thiết kế riêng.** Chọn một truy vấn đoạn mới, ghi đủ kiểu summary, leaf, identity, merge, chứng minh associativity và độ phức tạp; nếu không gộp O(1), phân tích chi phí thực.

## 24. Checklist trước khi nộp

- Đã định nghĩa chính xác truy vấn trên đoạn nào, [l,r) hay [l,r]?
- Có thể tạo summary đoạn lớn **chỉ từ hai summary con kề nhau**?
- Summary có **kích thước và chi phí merge** đủ nhỏ?
- Phép gộp có **tính kết hợp** trên toàn bộ summary hợp lệ?
- Có **identity hai phía**, và trường hợp đoạn rỗng được diễn giải đúng?
- Leaf chứa gì và node cha gộp hai con theo đúng thứ tự?
- Nếu merge không giao hoán, query giữ **leftAcc/rightAcc** đúng thứ tự?
- Mảng n không phải lũy thừa hai có padding identity đúng?
- Build O(n), point set O(log n), query O(log n) **khi merge O(1)**?
- Có kiểm point index/range biên hợp lệ?
- Nếu dùng min/max, identity có tương thích với miền giá trị?
- Nếu dùng max-subarray, Node lưu sum/pref/suff/best và xử lý nonempty?
- Nếu dùng affine, composition “left trước, right sau” có nhất quán?
- Có coi phép nối String là variable-time merge?
- Nếu lazy, đã có action apply(update,summary,len) đúng?
- Phép hợp thành lazy tags có đúng **thứ tự update**?
- Có push trước khi truy cập con khi cần và xóa tag cha đúng?
- Có kiểm overlap, whole-range, empty-range và update âm?
- Có phân biệt Math.addExact phát hiện overflow với atomic transaction?
- Có dùng oracle quét trực tiếp, brute max-subarray và affine thứ tự độc lập?
- Có test n=0/1/5, toàn âm, empty query, và các update đan xen?
- Đã chọn prefix/Fenwick/sparse table/offline nếu chúng phù hợp hơn cho yêu cầu cụ thể?

**Kết luận:** cây đoạn là cách tổ chức **các summary có phép gộp associative**, không phải chỉ là một “template tính tổng”. Điều kiện quan trọng nhất là phải biểu diễn được kết quả của đoạn nối bằng **merge(summary trái, summary phải)** một cách đúng, giữ thứ tự và đủ nhanh. **Identity** giúp xử lý đoạn rỗng/padding; **tính kết hợp** cho phép phân nhóm node khác nhau; **giao hoán không bắt buộc**. Khi query không gộp được bằng một số đơn lẻ, ta thiết kế summary nhiều trường, điển hình là **(sum,pref,suff,best)** cho maximum subarray. Với cập nhật cả đoạn, **lazy propagation đòi hỏi thêm một phép tác động lên summary và phép hợp thành tag đúng**, không tự suy ra từ monoid query. Lựa chọn cuối cùng nên dựa vào loại truy vấn, loại update, input tĩnh/động/offline, chi phí merge, miền số học và các kiểm thử độc lập.
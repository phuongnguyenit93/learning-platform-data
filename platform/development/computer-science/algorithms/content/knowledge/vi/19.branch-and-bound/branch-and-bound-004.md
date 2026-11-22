# Chọn nhánh theo chiều sâu, chiều rộng hoặc cận tốt nhất

**Nhánh và cận (branch and bound, B&B)** là kỹ thuật tìm kiếm chính xác trên không gian các lời giải tổ hợp. Ta **chia bài toán thành những bài toán con** (branching), tính một **cận lạc quan** cho kết quả tốt nhất có thể đạt được từ mỗi bài toán con (bounding), rồi **loại bỏ những nhánh không thể cải thiện nghiệm tốt nhất đã biết** (pruning).

Trong một lần chạy B&B, thường có nhiều **nút đang chờ được khám phá**. Ta cần chọn nút nào xử lý tiếp:

- **Theo chiều sâu (depth-first / DFS):** đi sâu vào một chuỗi quyết định, quay lui khi hết đường hoặc bị cắt.
- **Theo chiều rộng (breadth-first / BFS):** mở lần lượt các nút theo độ sâu tăng dần.
- **Theo cận tốt nhất (best-bound / best-first):** ưu tiên nút có **cận lạc quan hứa hẹn nhất**, bất kể nó ở độ sâu nào.

Ba chiến lược có thể dùng **cùng một cây tìm kiếm, cùng công thức cận, cùng quy tắc cắt nhánh** và đều tìm được nghiệm tối ưu nếu B&B được cài đúng. Chúng khác ở **thứ tự mở nút**, tốc độ phát hiện nghiệm khả thi tốt, số nút thực sự phải mở và lượng bộ nhớ dành cho những nhánh chưa xét.

Bài học lấy **bài toán ba lô 0/1** (0/1 knapsack) làm ví dụ xuyên suốt, vì nó cho thấy rõ ý nghĩa của **cận trên trong bài cực đại**. Cuối bài có chương trình Java 17+ chạy độc lập cả ba chiến lược, trả nghiệm tối ưu và thống kê tìm kiếm, cùng cách kiểm tra bằng vét cạn.

## 1. Cấu trúc chung của một thuật toán nhánh và cận

Giả sử bài toán cần **tối đa hóa** một mục tiêu value(x) với tập lời giải khả thi S.

Trong cây tìm kiếm, mỗi nút u đại diện cho một **tập những lời giải hoàn chỉnh còn có thể phát triển từ quyết định một phần của u**.

Một nút thường lưu:

- **State:** những quyết định đã cố định và thông tin ràng buộc tương ứng.
- **Bound(u):** một **cận trên** cho giá trị tốt nhất của mọi lời giải hoàn chỉnh nằm dưới u.
- **Candidate/Incumbent:** nghiệm khả thi tốt nhất đã phát hiện trên toàn bộ quá trình.
- **Children:** những trường hợp lựa chọn tiếp theo tạo thành các nhánh con.
- **Metadata:** độ sâu, quyết định đã chọn, hoặc thông tin dùng để phục hồi nghiệm.

Với bài **maximization**, nếu đã có nghiệm khả thi tốt nhất có giá trị **best**, và:

**upperBound(u) ≤ best**,

thì không có hậu duệ của u có thể tạo một giá trị **lớn hơn best**. Ta có thể **cắt bỏ toàn bộ nút u** nếu mục tiêu chỉ là tìm **một giá trị tối ưu/một nghiệm tối ưu**.

Với bài **minimization**, chiều bất đẳng thức đảo lại. Ta cần **lowerBound(u)** không lớn hơn chi phí nhỏ nhất có thể đạt được trong nhánh. Nếu:

**lowerBound(u) ≥ bestCost**,

ta có thể bỏ u khi chỉ cần một nghiệm có chi phí nhỏ nhất.

### Nhánh và cận không phải tìm kiếm mù

Một thuật toán vét cạn có thể sinh toàn bộ lá của cây rồi so các lời giải. B&B muốn tránh việc ấy nhờ cận: nhiều nút **không phải mở hết nhánh con** nếu đã biết chúng không thể cải thiện nghiệm hiện tại.

Điều kiện sống còn là **cận phải hợp lệ theo chiều lạc quan**:

- Với **max**, bound ≥ giá trị tốt nhất có thể có của mọi hậu duệ.
- Với **min**, bound ≤ chi phí nhỏ nhất có thể có của mọi hậu duệ.

Cận chỉ cần lạc quan **đủ để an toàn**, không cần chính xác tuyệt đối. Nhưng nếu cận quá lỏng, thuật toán có thể gần như vét cạn; nếu cận không hợp lệ (ví dụ cận trên lại thấp hơn nghiệm thật ở một nhánh), cắt nhánh có thể loại mất nghiệm tối ưu.

## 2. Nút sống, nghiệm tốt nhất và thứ tự chọn nhánh

Gọi **frontier**, **live nodes**, hoặc **danh sách chờ** là tập những nút đã được sinh nhưng chưa mở.

Quy trình chung:

~~~text
best = một nghiệm khả thi đã biết, hoặc nghiệm cơ sở
frontier = {root}

while frontier không rỗng:
    u = lấy một nút theo chiến lược đã chọn

    nếu bound(u) không thể cải thiện best:
        bỏ u
        continue

    nếu u đã hoàn tất:
        dùng lời giải của u để cập nhật best nếu tốt hơn
        continue

    sinh các lựa chọn con hợp lệ từ u
    với mỗi con v:
        nếu v là một nghiệm khả thi tốt hơn: cập nhật best
        nếu bound(v) vẫn có thể cải thiện best:
            đưa v vào frontier
        ngược lại:
            bỏ v

trả best
~~~

**Chính thao tác “lấy một nút từ frontier”** phân biệt DFS, BFS và best-bound. Quy tắc chia nhánh và hàm cận có thể giữ nguyên.

Có hai nơi thường cắt nhánh:

1. **Khi sinh con:** nếu bound(con)≤best, không cần lưu nó vào frontier.
2. **Khi lấy một nút ra:** best có thể đã tốt hơn từ lúc nút được đưa vào hàng chờ, nên kiểm tra bound một lần nữa để loại nút nay đã vô vọng.

Cắt ở cả hai thời điểm là an toàn và giúp giảm số nút phải mở. Nhưng nếu thống kê **số nút cắt**, phải mô tả rõ bạn có đếm cả nút bị loại ngay khi sinh hay không.

### Nghiệm incumbent phải thực sự khả thi

Một **cận trên** không phải một nghiệm thực tế. Không được dùng giá trị bound làm **best** nếu chưa xây được phương án khả thi có giá trị ấy. Trong bài ba lô 0/1, cận có thể giả định được lấy **một phần món đồ**; nhưng phương án cuối cùng chỉ được lấy **toàn bộ hoặc không lấy**.

Nếu dùng một giá trị lạc quan nhưng **không khả thi** làm incumbent, điều kiện cắt nhánh sẽ trở nên quá mạnh và có thể loại hết những nghiệm thật.

## 3. DFS: chọn nhánh theo chiều sâu

**Depth-first branch and bound** sử dụng cấu trúc **ngăn xếp LIFO**: nút được đưa vào cuối cùng thường được mở đầu tiên.

Quy trình:

1. Chọn nút đang chờ ở đỉnh stack.
2. Nếu cận tốt, sinh con.
3. Đưa con vào stack theo thứ tự sao cho **lựa chọn mong muốn** được khám phá trước.
4. Đi sâu đến khi gặp lá hoặc cận không đủ tốt.
5. Quay lui sang các nhánh chưa xét.

Nếu mỗi nút có tối đa hai con, muốn thử nhánh **chọn món** trước, khi dùng stack phải **đưa nhánh không chọn vào trước**, rồi đưa nhánh chọn vào sau. Nếu đảo thứ tự push, DFS thực tế sẽ khám phá nhánh còn lại trước.

### Ưu điểm của DFS

- **Bộ nhớ nhỏ:** nếu cây quyết định có độ sâu tối đa h và mỗi nút có số nhánh hữu hạn b, stack của DFS thường có cỡ **O(bh)**; trong cây nhị phân của ba lô 0/1 là **O(n)**.
- Có thể tìm một lời giải hoàn chỉnh khá sớm, nhất là khi **thứ tự nhánh** được thiết kế tốt.
- Nghiệm khả thi tốt xuất hiện sớm khiến **cắt nhánh mạnh hơn** ở những phần tiếp theo.
- Dễ cài bằng đệ quy hoặc stack tường minh; stack tường minh an toàn hơn nếu độ sâu quá lớn đối với ngăn xếp lời gọi Java.

### Nhược điểm của DFS

- Có thể đi **rất sâu vào nhánh kém** trước khi xét nhánh hứa hẹn hơn.
- Nếu thứ tự nhánh không tốt, có thể mất nhiều thời gian trước khi có incumbent mạnh.
- Nút với **cận rất tốt** ở một nhánh khác có thể phải chờ lâu.
- Không có bảo đảm DFS mở ít nút hơn BFS hay best-bound trong mọi đầu vào.

### Khi nào ưu tiên DFS?

DFS thường hợp lý khi bộ nhớ hạn chế, cây có độ sâu lớn, có heuristic sắp thứ tự lựa chọn tốt, hoặc khi có thể phát hiện nghiệm khả thi rất nhanh dọc một nhánh.

**DFS trong B&B không đồng nghĩa DFS thường:** nó vẫn phải tính **bound** và cắt nút có bound≤best. Nếu bỏ hoàn toàn cận, đây chỉ còn là tìm kiếm có quay lui/vét cạn theo chiều sâu.

## 4. BFS: chọn nhánh theo chiều rộng

**Breadth-first branch and bound** dùng **hàng đợi FIFO**. Nút sinh trước được mở trước, nên trong cây quyết định có mỗi tầng tương ứng một lựa chọn mới, thuật toán mở theo **độ sâu không giảm**.

Ví dụ cây nhị phân:

~~~text
                  root
               /        \
             A            B
           /   \        /   \
          C     D      E     F

DFS chọn trái trước: root, A, C, D, B, E, F
BFS:                 root, A, B, C, D, E, F
~~~

Đây chỉ là thứ tự minh họa trên cây chưa bị cắt; B&B thực tế có thể bỏ nhiều nút ngay khi thấy bound không đủ tốt.

### Ưu điểm của BFS

- Phủ nhiều lựa chọn ở **các tầng nông** trước khi đi sâu.
- Thứ tự mở nút dễ đoán, phù hợp với một số bài có nghiệm tốt xuất hiện ở độ sâu nhỏ.
- Dễ triển khai bằng queue và dễ minh họa cấu trúc cây quyết định.

### Nhược điểm của BFS

- **Bộ nhớ rất lớn** khi một tầng có nhiều nút sống: cây nhị phân có thể có Θ(2^h) nút ở tầng h.
- Có thể phải mở rất nhiều quyết định một phần trước khi đi tới nghiệm hoàn chỉnh.
- Việc tìm cận sớm không bảo đảm **nhanh tìm incumbent tốt** bằng DFS hay best-bound.
- Không tự tối ưu chỉ vì tên BFS: đây **không phải BFS tìm đường ngắn nhất trong đồ thị không trọng số** với điều kiện dừng khi gặp đích.

**BFS thường dùng trong tìm đường ngắn nhất** vì mọi cạnh có cùng chi phí và độ sâu chính là số bước. Nhưng trong B&B tối ưu tổ hợp, mục tiêu có thể là lợi nhuận, tổng chi phí hay số nhóm hoàn toàn **không bằng độ sâu cây quyết định**. Do đó **không được dừng tại lá đầu tiên của BFS** và tuyên bố tối ưu nếu chưa có lập luận cận thích hợp.

### Khi nào BFS có ý nghĩa?

BFS phù hợp nếu cần quan sát/sắp xếp tầng tìm kiếm, muốn giải các bài có cấu trúc theo số quyết định cố định, hoặc khi các tầng không quá rộng. Trong ba chiến lược chuẩn, BFS thường chịu **áp lực bộ nhớ** đáng kể nhất khi không có pruning mạnh.

## 5. Best-bound: chọn nút có cận tốt nhất

**Best-bound branch and bound** chọn **nút hứa hẹn nhất theo bound** thay vì theo thời điểm sinh hay độ sâu.

Với bài **max**, mỗi nút u có **upperBound(u)**. Chọn nút đang chờ có:

**upperBound(u) lớn nhất**.

Với bài **min**, dùng **lowerBound(u)** và chọn nút có:

**lowerBound(u) nhỏ nhất**.

Cấu trúc dữ liệu phù hợp là **priority queue / heap**. Đối với bài max, comparator ưu tiên bound giảm dần; đối với bài min, ưu tiên bound tăng dần.

~~~text
Với bài maximization:

frontier = max-priority-queue theo upperBound

while frontier chưa rỗng:
    u = pop node có upperBound lớn nhất

    nếu upperBound(u) <= incumbent:
        có thể bỏ u
        (hoặc kết thúc ngay nếu mọi nút còn lại có bound <= incumbent)

    nếu không:
        mở u, sinh nhánh con, cập nhật incumbent,
        đưa các con còn tiềm năng vào queue
~~~

### Vì sao có thể kết thúc sớm với best-bound?

Giả sử heap luôn bảo đảm nút đầu có **upperBound lớn nhất** trong tất cả nút đang chờ. Nếu:

**max_{u trong frontier} upperBound(u) ≤ best**,

thì **mọi nhánh chưa xét đều không thể cải thiện incumbent**. Ta đã có bằng chứng tối ưu và có thể dừng.

Với minimization, điều kiện tương ứng là:

**min_{u trong frontier} lowerBound(u) ≥ bestCost**.

Trong chương trình minh họa, ta vẫn lấy từng nút và đếm các nút bị bỏ để thống kê nhất quán; có thể tối ưu triển khai bằng cách dừng toàn bộ khi điều kiện trên đã được chứng minh.

### Ưu điểm và nhược điểm

Ưu điểm:

- Dồn công sức vào những vùng có **cận lạc quan mạnh**.
- Có thể sớm tìm được nghiệm tốt và sớm tạo **chứng nhận tối ưu** khi cận cao nhất không vượt incumbent.
- Phù hợp với các bài có **relaxation chặt** và biến thiên bound rõ ràng giữa các nhánh.

Nhược điểm:

- Cần quản lý **heap**, thao tác đưa/lấy tốn O(log M) với M là số nút chờ.
- Có thể giữ **rất nhiều nút sống** trong bộ nhớ, đặc biệt nếu cận lỏng.
- Cận cao không có nghĩa trong nhánh chắc chắn có nghiệm tốt; best-bound vẫn có thể khám phá nhánh kém.
- Không có định lý phổ quát rằng best-bound luôn mở ít nút hơn DFS/BFS. **Thứ tự sinh con, tie-breaker và incumbent** đều ảnh hưởng đến số nút được mở.

**Best-bound và A\*** có quan hệ ở việc ưu tiên theo đánh giá cận, nhưng không đồng nhất. A* tìm đường tối ưu dưới các giả thiết cụ thể về heuristic và đồ thị; best-bound B&B là cơ chế chọn nhánh trong một khung tìm kiếm tổ hợp rộng hơn.

## 6. So sánh ba chiến lược trước khi cài đặt

| Tiêu chí | DFS | BFS | Best-bound |
| --- | --- | --- | --- |
| Chọn nút tiếp theo | Nút mới sinh ở đỉnh stack | Nút sinh sớm nhất trong queue | Nút có cận lạc quan tốt nhất |
| Cấu trúc | Stack / đệ quy | Queue | Priority queue / heap |
| Thứ tự ưu tiên | Đi sâu | Độ sâu tăng | Độ hứa hẹn của cận |
| Bộ nhớ trường hợp xấu | Thường O(bh) trên cây | Có thể hàm mũ | Có thể hàm mũ |
| Khả năng có incumbent sớm | Phụ thuộc thứ tự nhánh | Phụ thuộc hình dạng cây | Phụ thuộc độ chặt của cận |
| Phí quản lý frontier | O(1) mỗi push/pop | O(1) mỗi enqueue/dequeue | O(log M) mỗi offer/poll |
| Cắt nhánh | bound so với incumbent | Giống DFS | Giống DFS |
| Đúng tối ưu khi cận hợp lệ và duyệt đầy đủ | Có | Có | Có |

**Kết luận:** lựa chọn chiến lược là một quyết định **hiệu năng và bộ nhớ**, không phải một phép thay đổi mục tiêu bài toán. Cùng một bound hợp lệ, nếu duyệt đến khi không còn nút có thể cải thiện nghiệm, cả ba đều phải trả **cùng giá trị tối ưu**.

## 7. Ví dụ chuẩn: ba lô 0/1 (0/1 knapsack)

Có n món đồ. Món i có:

- **wᵢ > 0**: trọng lượng.
- **vᵢ > 0**: giá trị.
- **C ≥ 0**: sức chứa ba lô.

Mỗi món được lấy **toàn bộ hoặc không lấy**; không thể lấy hai lần cùng một món.

Tìm tập S các món sao cho:

**∑_{i trong S} wᵢ ≤ C**,

và tối đa hóa:

**∑_{i trong S} vᵢ**.

Một nghiệm khả thi ban đầu luôn là **ba lô rỗng**, trọng lượng 0 và giá trị 0. Đây là incumbent hợp lệ dù thường chưa tốt.

### Trạng thái tìm kiếm

Để tính bound dễ, ta sắp các món theo **mật độ giá trị**:

**densityᵢ = vᵢ/wᵢ**, giảm dần.

Mỗi nút chứa:

- **level:** số món đầu theo thứ tự đã được quyết định; món tiếp theo có chỉ số level.
- **weight:** tổng trọng lượng đã chọn.
- **profit:** tổng giá trị đã chọn.
- **mask/parent decisions:** thông tin phục hồi các món đã chọn.
- **upperBound:** giá trị lớn nhất lạc quan có thể đạt từ nút.

Tại nút level=t, nhánh đôi:

1. **Lấy** món t nếu thêm vào không vượt sức chứa.
2. **Bỏ qua** món t.

Hai trường hợp bao phủ toàn bộ những cách chọn 0/1 còn lại và không trùng nhau. Mỗi lần chuyển level tăng 1; cây quyết định có độ sâu n.

### Vì sao cần giữ chỉ số món gốc?

Khi sắp xếp theo density, thứ tự duyệt không còn là thứ tự đầu vào. Nếu muốn xuất món 1,3,5 theo thứ tự input, trạng thái phải mang **id gốc** hoặc một ánh xạ từ chỉ số đã sắp sang chỉ số gốc.

Chương trình Java bên dưới giữ originalIndex và một bitmask để trả danh sách số thứ tự món **1-based theo đầu vào**, không phụ thuộc vào thứ tự khám phá.

## 8. Cận trên fractional knapsack: một phép nới lỏng hợp lệ

Để cắt nhánh trong bài ba lô **0/1 maximization**, cần cận trên cho **mọi cách hoàn thành từ nút hiện tại**.

Ý tưởng: tạm cho phép **lấy một phần món cuối**. Đây là bài **fractional knapsack**, có tập phương án **rộng hơn** bài 0/1, nên lợi nhuận tối ưu fractional **không nhỏ hơn** lợi nhuận tối ưu 0/1.

### Cách tính bound

Giả sử tại nút u:

- Đã dùng weight[u] và đạt profit[u].
- Dung lượng còn lại **room = C−weight[u]**.
- Chỉ được xét các món chưa quyết định, đã sắp theo v/w giảm dần.

Thực hiện:

1. Bắt đầu upper=profit[u].
2. Duyệt các món còn lại theo density giảm dần.
3. Nếu món vừa khít hoặc nhẹ hơn room, lấy toàn món: upper+=value và giảm room.
4. Nếu món nặng hơn room, cộng thêm **room/weight × value** như được phép lấy một phần, rồi dừng.
5. Nếu dùng giá trị nguyên, có thể làm tròn **lên** cận fractional để không đánh giá thấp nghiệm tối ưu nguyên.

Với một phần cuối có giá trị v, trọng lượng w, phòng trống r:

**fractionContribution = ceil(r×v/w)**.

Khi mọi giá trị món là số nguyên không âm, một cận nguyên hợp lệ là:

**upperBound = profit + tổng giá trị các món fractional lấy trọn + ceil(r×v/w)**.

Vì làm tròn lên, cận vẫn lạc quan. **Không được làm tròn xuống** một cách tùy ý khi dùng cận như số nguyên vì có thể mất tính an toàn trong những biến thể giá trị không nguyên hoặc công thức không chính xác.

### Điều kiện khiến phép thư giãn đúng

- Các món có **trọng lượng dương**, giá trị dương.
- Các món còn lại được xử lý theo **density giảm dần** để greedy fractional đạt optimum của bài nới lỏng.
- Chỉ đưa vào bound các món **chưa được quyết định**.
- Không cho phép lấy phần của món đã bị nhánh cha đánh dấu **bỏ qua**.
- Khi đã dùng đầy sức chứa, upper=profit hiện tại.
- Nếu trạng thái vượt sức chứa, đó là nhánh **bất khả thi**, loại ngay thay vì tính một bound giả.

### Vì sao sắp sai density nguy hiểm?

Một cận cần là **giới hạn trên của optimum**. Nếu chạy thuật toán chọn phần kiểu greedy nhưng các món chưa được sắp đúng mật độ, tổng fractional thu được có thể **thấp hơn optimum fractional**, thậm chí thấp hơn một nghiệm 0/1 tốt. Khi đó phép cắt dựa trên kết quả này có thể loại nhánh tối ưu.

Với các món nguyên dương, so sánh hai mật độ v₁/w₁ và v₂/w₂ có thể tránh sai số floating-point bằng cách so sánh tích chéo:

**v₁×w₂** và **v₂×w₁**.

Mã dùng phép nhân long trên các giá trị int dương, an toàn đối với tích của **hai số nguyên int dương**. Những bài có giá trị vượt int hoặc phép tích vượt long cần dùng **BigInteger** hoặc phép so sánh chống tràn khác.

## 9. Truy vết ví dụ và sự khác biệt thứ tự tìm kiếm

Cho C=9 và các món theo thứ tự đầu vào:

| ID món | Trọng lượng | Giá trị | Mật độ v/w |
| ---: | ---: | ---: | ---: |
| 1 | 2 | 3 | 1,5 |
| 2 | 3 | 4 | 1,333… |
| 3 | 4 | 5 | 1,25 |
| 4 | 5 | 8 | 1,6 |
| 5 | 1 | 2 | 2,0 |
| 6 | 6 | 10 | 1,666… |

Thứ tự xét theo mật độ giảm dần:

**5 → 6 → 4 → 1 → 2 → 3**.

Một nghiệm tối ưu là chọn các món **{1,5,6}**:

**Tổng trọng lượng = 2+1+6=9**.

**Tổng giá trị = 3+2+10=15**.

Ví dụ này phù hợp để so chiến lược vì nhánh lấy các món có density cao được thử sớm trong DFS, nhưng BFS vẫn phải mở nhiều nút nông trước khi khám phá sâu.

### Cận tại gốc

Sức chứa C=9. Theo density, ta có thể lấy:

- Món 5: trọng lượng 1, giá trị 2.
- Món 6: trọng lượng 6, giá trị 10.
- Phòng trống còn 2. Món 4 nặng 5, giá trị 8, lấy phần 2/5 theo relaxation → giá trị 3,2.

Vậy fractional upper = 2+10+3,2=15,2.

**Cận nguyên làm tròn lên =16**.

Nghiệm tối ưu nguyên bằng 15, nên bound=16 là **lạc quan nhưng hợp lệ**. Nó không phải một nghiệm khả thi có giá trị 16.

### Cùng bài toán, khác thứ tự mở nút

Trong chương trình ở mục 10, các tiêu chí thống kê được định nghĩa rõ:

- **expanded:** số nút thực sự được lấy ra và phát sinh nhánh con.
- **generated:** số nút con **khả thi theo sức chứa** được tạo, bất kể sau đó bị cắt hay được đưa vào frontier.
- **pruned:** đếm nhánh lấy món **bất khả thi**, nút con bị chặn ngay khi sinh và nút chờ bị loại khi lấy ra do incumbent đã tăng.
- **peakFrontier:** số nút chờ lớn nhất trong stack/queue/heap, tính cả nút gốc.

Bảng kết quả của một triển khai xác định (DFS thử nhánh lấy trước, BFS FIFO, best-bound dùng bound lớn nhất và phá hòa theo thứ tự sinh):

| Chiến lược | Giá trị tối ưu | Món được chọn | expanded | generated | pruned | peakFrontier |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| DFS | **15** | [1,5,6] | **4** | 7 | 5 | 3 |
| BFS | **15** | [1,5,6] | **8** | 14 | 9 | 5 |
| Best-bound | **15** | [1,5,6] | **6** | 11 | 7 | 5 |

**Lưu ý:** Đây là thống kê cho đúng quy tắc sinh con và cập nhật incumbent của mã minh họa; không phải định luật rằng DFS luôn tốt hơn best-bound. Trên đầu vào khác, best-bound có thể mở ít nút hơn cả DFS. Nếu thay cách phá hòa của heap, cách cập nhật incumbent hoặc cách đếm pruned, các con số thống kê cũng có thể đổi, dù **giá trị tối ưu bắt buộc vẫn là 15**.

## 10. Java 17+: so sánh DFS, BFS và best-bound trên cùng mã

Chương trình dưới đây không cần thư viện ngoài JDK. Nó có:

- Một hàm bound dùng fractional knapsack với các món sắp đúng mật độ.
- Cùng cách sinh hai nhánh **lấy / không lấy**.
- Ba cấu trúc frontier: **ArrayDeque như stack**, **ArrayDeque như queue**, **PriorityQueue theo upper bound**.
- Cập nhật incumbent ngay khi sinh một trạng thái khả thi có lợi nhuận tốt hơn.
- Cắt nhánh khi bound≤incumbent, kể cả với những nút chờ đã trở nên vô vọng.
- Trả danh sách món theo **ID gốc** bằng bitmask. Để minh họa gọn, giới hạn **n≤60** món; bài nhiều món hơn có thể dùng BitSet hoặc chuỗi parent.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.Deque;
import java.util.List;
import java.util.PriorityQueue;

public class BranchSelectionDemo {

    enum Policy { DFS, BFS, BEST_BOUND }

    record Item(int id, int weight, int value) {}

    record Node(int level, int weight, long profit,
                long bound, long mask, long serial) {}

    record Result(long value, int weight, List<Integer> chosen,
                  int expanded, int generated, int pruned,
                  int peakFrontier) {}

    // Exact density order for positive int weights and values.
    static Item[] sortedItems(int[] weights, int[] values) {
        if (weights == null || values == null
                || weights.length != values.length
                || weights.length > 60) {
            throw new IllegalArgumentException(
                    "Expected equally sized arrays with at most 60 items");
        }

        Item[] items = new Item[weights.length];
        for (int i = 0; i < items.length; i++) {
            if (weights[i] <= 0 || values[i] <= 0) {
                throw new IllegalArgumentException(
                        "Weights and values must be positive");
            }
            items[i] = new Item(i, weights[i], values[i]);
        }

        Arrays.sort(items, (a, b) -> {
            long left = (long) a.value() * b.weight();
            long right = (long) b.value() * a.weight();
            int cmp = Long.compare(right, left);
            return cmp != 0 ? cmp
                    : Integer.compare(a.id(), b.id());
        });

        return items;
    }

    // Upper bound from fractional knapsack, rounded UP to long.
    // Precondition: items are in descending value/weight order.
    static long upperBound(Item[] items, int capacity,
                           int level, int weight, long profit) {
        long result = profit;
        long room = (long) capacity - weight;

        for (int i = level; i < items.length && room > 0; i++) {
            Item item = items[i];

            if (item.weight() <= room) {
                room -= item.weight();
                result += item.value();
            } else {
                long numerator = room * item.value()
                        + item.weight() - 1L;
                result += numerator / item.weight();
                break;
            }
        }
        return result;
    }

    static Result solve(int[] weights, int[] values,
                        int capacity, Policy policy) {
        if (capacity < 0 || policy == null) {
            throw new IllegalArgumentException(
                    "Invalid capacity or policy");
        }

        Item[] items = sortedItems(weights, values);
        int n = items.length;

        Deque<Node> deque = policy == Policy.BEST_BOUND
                ? null : new ArrayDeque<>();

        PriorityQueue<Node> priority =
                policy == Policy.BEST_BOUND
                ? new PriorityQueue<>(
                    Comparator.<Node>comparingLong(Node::bound)
                        .reversed()
                        .thenComparingLong(Node::serial))
                : null;

        long serial = 0;
        Node root = new Node(0, 0, 0,
                upperBound(items, capacity, 0, 0, 0),
                0L, serial++);

        if (priority != null) {
            priority.add(root);
        } else {
            deque.addLast(root);
        }

        long bestValue = 0;
        int bestWeight = 0;
        long bestMask = 0;

        int expanded = 0;
        int generated = 0;
        int pruned = 0;
        int peakFrontier = 1;

        while (priority != null
                ? !priority.isEmpty() : !deque.isEmpty()) {

            Node node;
            if (priority != null) {
                node = priority.poll();
            } else if (policy == Policy.DFS) {
                node = deque.removeLast();
            } else {
                node = deque.removeFirst();
            }

            // Its bound may now be obsolete due to a better incumbent.
            if (node.bound() <= bestValue) {
                pruned++;
                continue;
            }

            if (node.level() == n) {
                continue;
            }

            expanded++;
            Item current = items[node.level()];
            List<Node> children = new ArrayList<>(2);

            // Branch 1: include this item, if feasible.
            long newWeight = (long) node.weight()
                    + current.weight();

            if (newWeight <= capacity) {
                int weight = (int) newWeight;
                long value = node.profit() + current.value();
                long mask = node.mask()
                        | (1L << current.id());

                // A partial selected set is already a feasible
                // knapsack solution (skip all undecided items).
                if (value > bestValue) {
                    bestValue = value;
                    bestWeight = weight;
                    bestMask = mask;
                }

                children.add(new Node(
                        node.level() + 1, weight, value,
                        upperBound(items, capacity,
                                node.level() + 1, weight, value),
                        mask, serial++));
                generated++;
            } else {
                // Infeasible include branch.
                pruned++;
            }

            // Branch 2: exclude this item.
            children.add(new Node(
                    node.level() + 1,
                    node.weight(), node.profit(),
                    upperBound(items, capacity,
                            node.level() + 1,
                            node.weight(), node.profit()),
                    node.mask(), serial++));
            generated++;

            // Stack is LIFO: push exclude first to visit
            // include first. Other policies see normal order.
            if (policy == Policy.DFS) {
                Collections.reverse(children);
            }

            for (Node child : children) {
                if (child.bound() > bestValue
                        && child.level() < n) {

                    if (priority != null) {
                        priority.add(child);
                        peakFrontier = Math.max(
                                peakFrontier, priority.size());
                    } else {
                        deque.addLast(child);
                        peakFrontier = Math.max(
                                peakFrontier, deque.size());
                    }
                } else {
                    pruned++;
                }
            }
        }

        List<Integer> chosen = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            if ((bestMask & (1L << i)) != 0L) {
                chosen.add(i + 1);
            }
        }

        return new Result(
                bestValue, bestWeight, List.copyOf(chosen),
                expanded, generated, pruned, peakFrontier);
    }

    public static void main(String[] args) {
        int[] weights = {2, 3, 4, 5, 1, 6};
        int[] values = {3, 4, 5, 8, 2, 10};
        int capacity = 9;

        for (Policy policy : Policy.values()) {
            System.out.println(policy + ": "
                    + solve(weights, values, capacity, policy));
        }

        int[] w2 = {2, 5, 10, 5};
        int[] v2 = {40, 30, 50, 10};

        for (Policy policy : Policy.values()) {
            System.out.println("Case B " + policy + ": "
                    + solve(w2, v2, 16, policy));
        }

        System.out.println("Empty: "
                + solve(new int[] {}, new int[] {},
                        10, Policy.DFS));
    }
}
~~~

Lưu thành **BranchSelectionDemo.java**, biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac BranchSelectionDemo.java
java BranchSelectionDemo
~~~

**Đầu ra chính xác theo thứ tự chiến lược và quy tắc thống kê của chương trình:**

~~~text
DFS: Result[value=15, weight=9, chosen=[1, 5, 6], expanded=4, generated=7, pruned=5, peakFrontier=3]
BFS: Result[value=15, weight=9, chosen=[1, 5, 6], expanded=8, generated=14, pruned=9, peakFrontier=5]
BEST_BOUND: Result[value=15, weight=9, chosen=[1, 5, 6], expanded=6, generated=11, pruned=7, peakFrontier=5]
Case B DFS: Result[value=90, weight=12, chosen=[1, 3], expanded=6, generated=10, pruned=7, peakFrontier=3]
Case B BFS: Result[value=90, weight=12, chosen=[1, 3], expanded=6, generated=10, pruned=7, peakFrontier=3]
Case B BEST_BOUND: Result[value=90, weight=12, chosen=[1, 3], expanded=5, generated=8, pruned=6, peakFrontier=3]
Empty: Result[value=0, weight=0, chosen=[], expanded=0, generated=0, pruned=1, peakFrontier=1]
~~~

### Giải thích các phần then chốt của mã

**sortedItems:** sắp các món theo giá trị/trọng lượng giảm dần bằng **tích chéo long**, không dựa vào phép so sánh double. Mỗi Item vẫn giữ ID gốc để khôi phục danh sách món như đầu vào.

**upperBound:** bắt đầu từ profit hiện có, rồi cho phép lấy trọn hoặc một phần các món **chưa quyết định**. Dùng làm tròn lên của phần cuối để bảo đảm cận nguyên vẫn không đánh giá thấp lợi nhuận tốt nhất có thể có.

**Node:** ghi level, weight, profit, bound, mask, serial. Trường serial giúp best-bound phá hòa theo **thứ tự sinh nút**, nên thứ tự và các số thống kê của ví dụ không bị phụ thuộc cách heap xử lý các node có cùng bound.

**Incumbent:** cập nhật ngay khi sinh một nhánh **lấy món khả thi** có profit tốt hơn. Dù chưa quyết định hết n món, tập món đã chọn đã là một nghiệm hợp lệ vì có thể bỏ tất cả các món còn lại.

**DFS:** dùng removeLast. Sau khi sinh con theo [lấy,bỏ], chương trình đảo thứ tự chèn để **lấy** được duyệt trước.

**BFS:** dùng removeFirst và chèn con vào cuối deque; nhờ đó các tầng được xử lý theo độ sâu tăng dần.

**BEST_BOUND:** dùng PriorityQueue theo bound giảm dần, hòa theo serial nhỏ hơn. Best-bound có thể ưu tiên một nhánh sinh muộn nhưng bound cao hơn nhánh sinh sớm.

**Pruning:** nhánh lấy món vượt sức chứa bị bỏ ngay. Con có bound≤best không được đưa vào frontier. Nếu một node đã vào frontier nhưng incumbent cải thiện sau đó, nó có thể bị loại khi pop. Chương trình đếm cả các loại bỏ này vào pruned; cách quy ước đếm node khác sẽ cho con số khác nhưng không thay đổi kết quả tối ưu.

**Giới hạn n≤60:** mask kiểu long lưu vị trí món gốc. Nếu bài có hàng trăm món, nên dùng BitSet hoặc chuỗi parent thay vì mở rộng bằng dịch bit quá xa. Mọi trọng lượng/giá trị trong bản minh họa phải là **số nguyên dương** và sức chứa không âm.

## 11. Chứng minh tính đúng: phần nào không phụ thuộc chiến lược?

Có ba thành phần cần chứng minh:

### 11.1. Phân nhánh bao phủ mọi lời giải

Mỗi món 0/1 được xét đúng một lần. Tại món t, mọi nghiệm hoàn chỉnh hoặc **chứa** món t hoặc **không chứa** món t. Hai lựa chọn rời nhau, nên hai nhánh con bao phủ toàn bộ các nghiệm hoàn chỉnh xuất phát từ trạng thái cha.

Nếu nhánh lấy món t làm tổng trọng lượng vượt C, với các trọng lượng đều dương, mọi lời giải phát triển từ nhánh đó cũng vượt C, nên loại nhánh là an toàn.

### 11.2. Cận không đánh giá thấp hậu duệ tối ưu

Giữ cố định những món đã lấy và đã bỏ của một nút. Mọi phương án 0/1 của các món còn lại cũng là một phương án hợp lệ của **bài toán nới lỏng cho phép lấy một phần món cuối**. Optimum của fractional knapsack không nhỏ hơn optimum 0/1 của cùng phần việc.

Sắp theo density giảm dần là tối ưu cho fractional knapsack. Làm tròn lên giá trị fractional cuối tạo cận nguyên **không thấp hơn** optimum fractional. Do đó:

**upperBound(node) ≥ profit của mọi nghiệm hoàn chỉnh dưới node**.

### 11.3. Cắt khi bound≤incumbent không bỏ mất giá trị tối ưu

Incumbent bestValue luôn đến từ **một tập món khả thi**. Nếu bound(u)≤bestValue, mọi hậu duệ của u có profit≤bound(u)≤bestValue, nên không có hậu duệ nào có thể cải thiện incumbent. Bỏ u không thể làm mất một nghiệm có giá trị lớn hơn bestValue.

Tại kết thúc, mọi nhánh hoặc đã được xử lý, hoặc đã được chứng minh không có nghiệm vượt incumbent. Vì thế incumbent chính là **giá trị tối ưu toàn cục**.

**Thứ tự lấy nút không xuất hiện trong chứng minh:** DFS, BFS hay best-bound chỉ thay đổi thứ tự duyệt những nhánh chưa bị chứng minh vô vọng. Nếu tất cả thao tác bound, feasibility và incumbent đều đúng, cả ba trả cùng optimum.

### Khi có nhiều nghiệm đồng tối ưu

Trong mã, chỉ cập nhật nếu **value > bestValue**, và cắt khi **bound≤bestValue**. Vì vậy mã chỉ hứa trả **một nghiệm tối ưu**, không liệt kê mọi nghiệm đạt cùng giá trị. Nếu muốn tìm **tất cả** các nghiệm tối ưu hoặc tối ưu thêm tiêu chí thứ hai, không thể tự giữ điều kiện cắt dấu bằng mà không xét lại mục tiêu.

## 12. Vai trò của cận mạnh, cận yếu và incumbent ban đầu

Hai yếu tố chính quyết định hiệu quả pruning:

1. **Độ chặt của bound.** Cận trên càng gần optimum thật của nhánh, càng dễ phát hiện nhánh không thể thắng best.
2. **Chất lượng incumbent.** Best càng cao (trong maximization), càng nhiều nhánh có bound≤best.

Ví dụ:

- Nếu một nhánh có optimum thật bằng 20 nhưng upperBound=10.000, bound đúng nhưng **rất lỏng**; nhiều node con sẽ được mở trước khi biết nhánh không thể vượt incumbent.
- Nếu cùng nhánh có upperBound=21 và incumbent=22, ta cắt ngay.
- Nếu upperBound=21 nhưng incumbent chỉ bằng 5, vẫn phải giữ nhánh vì nó có thể vượt 5.

### Khởi tạo incumbent bằng heuristic

Ngoài nghiệm rỗng, có thể chạy nhanh một heuristic để tìm một phương án khả thi, chẳng hạn greedy chọn các món theo density cho đến khi hết chỗ. Nghiệm greedy có thể **không tối ưu** nhưng tạo một **lower bound khả thi** (đối với maximization) giúp cắt nhiều nhánh hơn.

Phải phân biệt:

- **Giá trị của nghiệm greedy 0/1 hợp lệ**: có thể làm incumbent.
- **Giá trị fractional knapsack**: chỉ là upperBound, **không được** làm incumbent.

Nếu heuristic dùng đầu vào lớn hoặc có ràng buộc phức tạp, cần luôn **kiểm tra lại tính khả thi** trước khi dùng làm incumbent.

### Tác động của thứ tự nhánh

Với DFS, ưu tiên nhánh **lấy món mật độ cao trước** thường giúp thấy nghiệm tốt sớm, nhưng không phải luôn tối ưu. Với best-bound, priority queue tự ưu tiên bound cao; tuy nhiên thứ tự sinh và tie-break vẫn ảnh hưởng số node do cách cập nhật incumbent.

Có thể áp dụng **branching heuristic** để chọn biến/món tiếp theo hứa hẹn nhất thay vì luôn chọn món đầu theo mật độ. Khi đổi branching heuristic, phải cập nhật đúng ý nghĩa level, các món chưa xét và cách tính bound; không thể giữ nguyên công thức chia theo “món tiếp theo” nếu cấu trúc đã thay đổi.

## 13. Ví dụ minh họa: best-bound không luôn vượt DFS

Ở bộ thứ nhất C=9, kết quả thống kê:

~~~text
DFS expanded=4
BFS expanded=8
BEST_BOUND expanded=6
~~~

Ở đây DFS tìm nhanh nghiệm 15 theo nhánh lấy-món-trước, khiến nhiều nhánh bị cắt ngay. Best-bound quan tâm bound của các nút khác nên có thể mở nhiều hơn DFS.

Ở bộ thứ hai:

~~~text
weights = [2,5,10,5]
values  = [40,30,50,10]
capacity= 16

Optimum = 90, chọn món [1,3], tổng trọng lượng 12.

DFS expanded=6
BFS expanded=6
BEST_BOUND expanded=5
~~~

Best-bound lần này mở ít nút hơn cả DFS và BFS.

Không có mâu thuẫn: **cùng một hàm bound và cùng bài toán** nhưng những cấu trúc cây khác nhau khiến việc ưu tiên theo cận hay đi sâu có hiệu quả khác nhau. Khi thiết kế thuật toán thực tế, nên **đo số expanded, số pruned, peakFrontier và thời gian chạy** trên các nhóm dữ liệu khác nhau, chứ không dựa vào một ví dụ rồi tuyên bố chiến lược nào luôn nhanh nhất.

### Thống kê hiệu năng không phải thước đo duy nhất

- **Expanded thấp** nhưng heap thao tác đắt vẫn có thể có thời gian thực cao.
- **PeakFrontier cao** có thể gây hết RAM trước khi thuật toán chứng minh tối ưu.
- Bound rất mạnh nhưng mỗi lần tính quá tốn CPU có thể chậm hơn bound lỏng tính rẻ.
- Heuristic tốt có thể làm thay đổi hẳn số node mở của cùng một chiến lược.

Cần đo trên cùng phần cứng và cùng cách cài đặt, định nghĩa thống kê rõ ràng; không nên so số expanded từ hai chương trình khác nhau nếu chúng dùng quy tắc cắt nhánh khác nhau.

## 14. Độ phức tạp theo n và kích thước frontier

Ba lô 0/1 có **2^n tập con** có thể chọn, và cây quyết định đầy đủ có O(2^n) nút. Branch and bound **không bảo đảm thời gian đa thức** trong trường hợp xấu nhất; nếu bound không cắt đáng kể, vẫn có thể phải khám phá gần hết cây.

Trong bản mã:

- Sắp xếp n món theo density: **O(n log n)**.
- Mỗi lần tính fractional upperBound quét tối đa n−level món, tức **O(n)**.
- Số node trong cây đầy đủ là O(2^n), nên số thao tác bound có thể đến **O(n2^n)**.
- DFS/BFS có thao tác push/pop của deque **O(1)**.
- Best-bound có thêm **O(log M)** cho mỗi offer/poll với M là kích thước heap tại thời điểm đó. Tổng số thao tác heap trong trường hợp xấu nhất vẫn bị chi phối bởi quy mô tìm kiếm hàm mũ.

Bộ nhớ:

- **DFS:** nếu mỗi node chỉ sinh hai con và dùng LIFO đúng cách, số nút đang chờ trên một đường tìm kiếm thường **O(n)**; còn thêm dữ liệu các món và thống kê.
- **BFS:** có thể phải giữ một tầng chứa **Θ(2^n)** nút sống trong cây nhị phân.
- **Best-bound:** heap có thể giữ **O(2^n)** nút sống; không có cận bộ nhớ nhỏ kiểu DFS.

Cận bộ nhớ nói về **frontier**, không tính bộ nhớ của mọi trạng thái đã duyệt nếu một cài đặt tự lưu lịch sử, bảng băm hoặc cây tìm kiếm đầy đủ. Mã chỉ giữ frontier và incumbent nên không cần giữ tất cả các node đã xử lý.

### Vì sao cùng O(2^n) nhưng thời gian thực khác xa?

Big-O là cận xấu nhất. Trên dữ liệu cụ thể, một incumbent tốt và bound chặt có thể cắt phần lớn cây; số expanded giảm rất sâu. Ngược lại, một số dữ liệu có nhiều phương án gần tối ưu khiến bound gần nhau, làm heap lớn và pruning yếu.

Bởi vậy B&B là một thuật toán **exact exponential search với pruning**, không phải lời giải đa thức bảo đảm cho mọi trường hợp của 0/1 knapsack.

## 15. Thay đổi khi bài toán cần cực tiểu hóa

Giả sử mục tiêu là **minimize cost** (ví dụ TSP, lịch trình, chi phí phân công):

- Incumbent **bestCost** là chi phí của một **phương án hoàn chỉnh hợp lệ** đã biết.
- Một node phải có **lowerBound(node)** không lớn hơn chi phí thấp nhất của mọi lời giải hoàn chỉnh bên dưới.
- **Prune nếu lowerBound(node)≥bestCost**.
- **Best-bound ưu tiên node có lowerBound nhỏ nhất**.

Ví dụ TSP: cận dưới có thể đến từ một bài toán nới lỏng về cây khung hoặc phép gán, tùy thuật toán. Một cận hợp lệ phải phản ánh ràng buộc rằng đường đi hoàn chỉnh còn cần nối các thành phần chưa ghé; không được coi chi phí đã đi là một nghiệm tour hoàn chỉnh nếu đường chưa khép lại.

### Đừng đảo dấu một cách máy móc

Với maximization:

~~~text
incumbent = gia tri kha thi cao nhat da tim
bound(u)  = upper bound cua cac nghiem trong u
cat neu bound(u) <= incumbent
best-bound pop bound LON NHAT
~~~

Với minimization:

~~~text
incumbent = chi phi kha thi nho nhat da tim
bound(u)  = lower bound cua cac nghiem trong u
cat neu bound(u) >= incumbent
best-bound pop bound NHO NHAT
~~~

Trong cả hai, “best” là chất lượng của **nghiệm khả thi**, còn “bound” là **ước lượng lạc quan** của một vùng tìm kiếm. Nhầm hai vai trò này là lỗi nguy hiểm nhất của B&B.

## 16. Liên hệ với backtracking, BFS, greedy và A*

**Backtracking:** thường dùng nhánh theo chiều sâu và cắt bằng các ràng buộc bất khả thi. Branch and bound thêm cơ sở cắt **theo cận của hàm mục tiêu**, không chỉ theo tính hợp lệ. Một thuật toán có thể vừa backtracking vừa B&B.

**BFS trên đồ thị:** phục vụ duyệt theo lớp hoặc tìm số cạnh ít nhất trong đồ thị không trọng số. Trong B&B, BFS chỉ là **một chính sách mở nút**. Độ sâu của nút không đương nhiên là giá trị mục tiêu.

**Greedy:** chọn một quyết định cục bộ và không giữ đầy đủ lựa chọn thay thế; có thể tìm nghiệm nhanh nhưng thường không chứng minh tối ưu cho bài ba lô 0/1. Greedy có thể dùng **để khởi tạo incumbent** hoặc xây bound fractional, nhưng hai vai trò này khác nhau.

**A\*:** thường chọn trạng thái theo f=g+h và dùng heuristic **admissible** để tìm đường tối ưu. B&B best-bound cũng ưu tiên theo cận, nhưng không có nghĩa mọi chương trình PriorityQueue trong B&B là A*, hoặc phải tuân theo cùng mô hình đồ thị/trọng số.

**Dynamic programming:** gom những bài toán con trùng nhau theo trạng thái, lưu kết quả để tránh tính lại. B&B tập trung vào **loại bỏ vùng lời giải bằng cận**. Hai kỹ thuật có thể kết hợp: memoization/dominance xử lý trạng thái trùng, bound cắt những vùng không thể thắng incumbent.

Trong các bài khó, hiệu quả lớn thường đến từ **cận tốt + heuristic tốt + chiến lược frontier phù hợp**, chứ không chỉ thay stack bằng heap.

## 17. Cải tiến nâng cao: dominance, warm start và tìm kiếm lai

### Dominance pruning

Hai node ở cùng mức quyết định t, với trạng thái A và B. Nếu:

- **weight(A)≤weight(B)**;
- **profit(A)≥profit(B)**;

thì A **trội hơn** B vì còn ít nhất bằng dung lượng trống nhưng đã có không ít lợi nhuận, và cả hai có **cùng tập món chưa quyết định**. Mọi phần còn lại khả thi cho B cũng khả thi cho A và cho lợi nhuận không thấp hơn. Khi chỉ cần **giá trị tối ưu**, có thể bỏ B nếu duy trì cấu trúc dominance đúng.

Tuy nhiên, A/B phải có **cùng danh sách quyết định còn lại**; nếu cùng weight/profit nhưng đã bỏ những món khác nhau, so sánh trực tiếp có thể sai. Khi bài có ràng buộc khác (số món tối đa, nhóm xung đột, thứ tự), cần đưa mọi thông tin liên quan vào điều kiện dominance.

### Warm start

Nếu có sẵn một lời giải tốt từ greedy hoặc lời giải cũ của bài toán gần tương tự, có thể dùng nó làm incumbent, **sau khi kiểm tra tính khả thi đối với dữ liệu hiện tại**. Incumbent càng mạnh, càng nhiều node bị cắt.

### Tìm kiếm lai

Một thiết kế thực tế có thể:

1. DFS nhanh để tìm incumbent tốt với ít RAM.
2. Chuyển sang best-bound để tập trung vào những node còn có bound cao.
3. Áp dụng giới hạn bộ nhớ hoặc kiểm soát frontier.

Tuy nhiên, nếu chuyển chính sách hoặc bỏ node do giới hạn RAM, phải bảo đảm những node đó đã được **chứng minh vô vọng**. Nếu chỉ loại các node hứa hẹn do hết bộ nhớ, thuật toán có thể trở thành heuristic **không còn bảo đảm tối ưu**.

### Tính toán bound tăng dần

Trong ba lô 0/1, upperBound của con có thể liên hệ với bound của cha. Các cài đặt tối ưu có thể duy trì dữ liệu tích lũy để tính bound nhanh hơn thay vì quét phần chưa quyết định từ đầu. Nhưng phải chứng minh cập nhật đúng khi một món đã bị chọn hoặc bị loại; một lỗi nhỏ có thể làm cận thấp hơn optimum.

## 18. Trường hợp biên và các lỗi cần tránh

| Trường hợp | Điều cần làm |
| --- | --- |
| **n=0** | Nghiệm rỗng, giá trị và trọng lượng bằng 0 |
| **C=0** và mọi trọng lượng dương | Chỉ có nghiệm rỗng, optimum=0 |
| **Món nặng hơn C** | Nhánh lấy món bất khả thi; nhánh bỏ vẫn hợp lệ |
| **Hai món cùng mật độ** | Dùng quy tắc hòa xác định; bound fractional vẫn đúng |
| **Nhiều nghiệm đồng tối ưu** | Mã trả một nghiệm, không bảo đảm liệt kê tất cả |
| **Bound bằng incumbent** | Có thể cắt nếu chỉ cần một optimum; cần xem lại nếu cần tất cả |
| **Không có incumbent ban đầu** | Với mô hình này, ba lô rỗng là một incumbent hợp lệ |
| **Trọng lượng 0 hoặc giá trị âm** | Bản minh họa không nhận; cần sửa mô hình bound nếu muốn hỗ trợ |
| **n>60** | Không dùng mask long hiện tại; cần BitSet/parent |
| **Tổng lợi nhuận vượt long** | Dùng kiểm tra tràn hoặc BigInteger |
| **Bound bằng số thực làm tròn sai** | Có thể gây cắt nhánh sai; dùng tính toán an toàn |
| **Frontier quá lớn** | Đánh giá bộ nhớ, không âm thầm bỏ node cần xét |

Các lỗi phổ biến:

1. **Dùng cận trên để cắt bài min** thay vì cận dưới.
2. **Lấy upperBound làm incumbent**, dù nó chỉ đến từ relaxation có thể không khả thi.
3. **Cắt khi bound có khả năng nhỏ hơn optimum thật** do công thức hoặc làm tròn sai.
4. **Sắp theo density sai** nhưng vẫn coi fractional greedy là cận trên tối ưu.
5. **Quên các món đã bỏ khi tính bound**; đưa chúng lại vào relaxation có thể làm bound quá lỏng hoặc làm lệch logic của state.
6. **Giữ các món vượt sức chứa trong nhánh chọn** thay vì cắt bất khả thi.
7. **Không kiểm tra bound của node chờ sau khi incumbent tăng**; vẫn mở những node đã vô vọng.
8. **Dùng BFS rồi dừng ngay ở lá đầu**, tưởng BFS bảo đảm optimum lợi nhuận.
9. **Sắp heap theo bound nhỏ nhất trong bài max**, khiến thứ tự trái ý định best-bound.
10. **Đưa nhánh lấy trước vào LIFO rồi mong lấy nó đầu tiên**; stack sẽ pop nhánh vừa push sau cùng.
11. **Không thống nhất cách đếm expanded/generated/pruned**, so sánh hiệu năng lệch.
12. **Không theo dõi originalIndex sau khi sort**, in ra món sai.
13. **Chỉ giữ bestValue mà không giữ phương án**, trong khi đề yêu cầu danh sách món.
14. **Tuyên bố best-bound luôn tốt nhất**, không xét input và hiệu ứng incumbent.
15. **Quên xét n=0 hoặc C=0**, dễ lỗi truy cập mảng hoặc trả nghiệm không hợp lệ.
16. **Quên tính chi phí heap và RAM**, chỉ nhìn số nút expanded.
17. **Dùng bound lỏng nhưng kỳ vọng thời gian đa thức** trên mọi ba lô 0/1.
18. **Không phát hiện overflow khi so density bằng tích chéo** với dữ liệu vượt miền int.
19. **Dùng điều kiện bound≤best nhưng lại cần tất cả nghiệm đồng tối ưu**; có thể bỏ nhánh chứa nghiệm bằng best.
20. **Bỏ node do giới hạn bộ nhớ mà vẫn tuyên bố đã chứng minh tối ưu**.

## 19. Kiểm thử correctness và thống kê

Để kiểm thử một B&B có nhiều chính sách frontier, hãy dùng một **bộ chuẩn độc lập** cho n nhỏ:

1. Duyệt mọi tập con món bằng mặt nạ từ 0 đến 2ⁿ−1.
2. Tính tổng trọng lượng và tổng giá trị.
3. Nếu trọng lượng≤C, cập nhật giá trị tốt nhất.
4. Chạy cả ba chiến lược B&B trên cùng dữ liệu.
5. So **bestValue của mỗi chiến lược** với optimum vét cạn.
6. Kiểm tra tập món in ra có trọng lượng và giá trị đúng, mỗi món chỉ xuất hiện một lần, và không vượt C.
7. Đo expanded, pruned, peakFrontier như **thống kê hiệu năng**; không lấy việc thống kê khác nhau làm dấu hiệu sai kết quả.

Ví dụ một bộ random test n≤12 có thể phát hiện các lỗi:

- Nhầm hướng so sánh trong priority queue.
- Thiếu nhánh bỏ món hoặc thêm món quá sức chứa.
- Upper bound sai ở một nhánh ít được khám phá.
- Cắt nút khi bound vẫn có thể thắng incumbent.
- Lỗi khôi phục mask sau khi đổi thứ tự theo density.
- Sai khi có món trùng mật độ, tất cả quá nặng hoặc C=0.

### Những phép kiểm tra không đủ

- Chỉ chạy DFS rồi tin BFS/best-bound giống nhau.
- Chỉ kiểm tra một ví dụ trên slide.
- Chỉ so optimum mà không kiểm tra **tính khả thi của món đã chọn**.
- Chỉ thấy số expanded của best-bound thấp hơn rồi kết luận bound đúng.
- Chỉ thấy nghiệm tốt sớm và kết thúc khi frontier còn node có upperBound>incumbent.

### Bất biến dùng cho debugging

Tại mọi thời điểm:

- **Incumbent** đến từ một tập món hợp lệ, nên bestValue không vượt optimum thật.
- Mọi nút còn sống có upperBound **không nhỏ hơn** optimum thật có thể đạt dưới chính nút đó.
- Nếu một node bị loại vì bound≤bestValue, toàn bộ phần lời giải dưới node đều không thể cải thiện bestValue.
- Tổng các nút đã xử lý, đã cắt và chưa xử lý bao phủ không gian nhánh theo cách không bỏ sót một nghiệm nào có thể thắng incumbent.

Bất biến thứ hai quan trọng nhất: **một cận sai có thể trả kết quả đúng trên hàng nghìn ca nhỏ** nhưng vẫn sai trên ca khác. Muốn tin B&B, cần chứng minh phép thư giãn hoặc bound an toàn, không chỉ dựa vào kiểm thử.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Trong bài maximization, một node có upperBound=50 và incumbent=52. Có cần mở node đó không?  
**Đáp án:** Không. Mọi nghiệm hoàn chỉnh dưới node có giá trị≤50≤52 nên không thể cải thiện incumbent.

**Câu 2.** Nếu đổi sang minimization, một node có lowerBound=80 và bestCost=75. Có thể cắt không?  
**Đáp án:** Có, vì mọi nghiệm trong node có chi phí ít nhất 80, không tốt hơn 75.

**Câu 3.** DFS, BFS, best-bound khác nhau ở bước nào trong khung B&B?  
**Đáp án:** **Chọn nút sống tiếp theo** từ frontier: LIFO, FIFO hoặc ưu tiên bound lạc quan tốt nhất.

**Câu 4.** Với DFS dùng stack, muốn thử nhánh “lấy món” trước thì đưa nhánh nào vào stack trước?  
**Đáp án:** Đưa nhánh **bỏ món** trước, nhánh lấy sau, vì LIFO lấy node vừa push sau cùng.

**Câu 5.** Vì sao fractional knapsack cho một upper bound của 0/1 knapsack?  
**Đáp án:** Nó nới lỏng ràng buộc chỉ được lấy trọn/không lấy, nên optimum bài fractional không nhỏ hơn optimum bài 0/1 của cùng các món còn lại.

**Câu 6.** Trong bộ ví dụ C=9, các món [1,5,6] có trọng lượng và giá trị bao nhiêu?  
**Đáp án:** Trọng lượng **2+1+6=9**, giá trị **3+2+10=15**.

**Câu 7.** Ba chiến lược có buộc phải mở cùng số node không?  
**Đáp án:** Không. Thứ tự mở node ảnh hưởng thời điểm incumbent tăng và lượng pruning, dù giá trị tối ưu cuối phải giống nhau.

**Câu 8.** Best-bound có luôn mở ít node hơn DFS không?  
**Đáp án:** Không. Trong ví dụ chính, DFS mở 4 node, best-bound mở 6 node.

**Câu 9.** Vì sao ưu tiên largest bound cho maximization nhưng smallest bound cho minimization?  
**Đáp án:** Vì bound lạc quan là **giới hạn trên** cho max và **giới hạn dưới** cho min; giá trị hứa hẹn nhất nằm ở đầu tương ứng.

**Câu 10.** Nếu cần tất cả các nghiệm đồng tối ưu, dùng điều kiện prune bound≤incumbent của bản mã có đủ không?  
**Đáp án:** Không. Nó có thể cắt những nhánh còn nghiệm đạt bằng incumbent, nên phải sửa tiêu chí cắt/thu thập nghiệm.

**Câu 11.** Trong cây nhị phân độ sâu n, frontier của DFS và BFS thường khác nhau thế nào ở trường hợp xấu?  
**Đáp án:** DFS thường có O(n) nút chờ; BFS có thể giữ Θ(2ⁿ) node ở một tầng.

**Câu 12.** Nếu đã có một nghiệm greedy 0/1 hợp lệ, dùng nó làm gì trong B&B?  
**Đáp án:** Làm **incumbent ban đầu** để tăng khả năng cắt nhánh, nhưng không dùng giá trị fractional không khả thi làm incumbent.

**Câu 13.** Nếu heap có một node đầu với upperBound≤bestValue, ta có thể kết thúc best-bound sớm không?  
**Đáp án:** Có nếu heap luôn giữ mọi nút sống và sắp **bound giảm dần**; khi đó mọi nút còn lại cũng không thể thắng bestValue.

**Câu 14.** Tại sao không được khẳng định thời gian B&B là O(n log n) chỉ vì đã sort món theo density?  
**Đáp án:** Sort chỉ là bước đầu. Số node của cây quyết định có thể hàm mũ và mỗi node còn phải tính bound, nên tổng thời gian trường hợp xấu vẫn có thể hàm mũ.

## 21. Bài tập mở rộng

1. Thay nghiệm rỗng bằng **greedy feasible incumbent** trước vòng B&B. Chạy lại ba chiến lược, ghi bảng expanded và peakFrontier trên dữ liệu nhỏ và dữ liệu n lớn hơn.
2. Thêm cách **khôi phục danh sách món bằng BitSet** hoặc chuỗi parent cho n>60, không đổi cách tính bound/prune.
3. Chuyển chương trình sang **minimization** của một bài phân công nhỏ: tự xây lowerBound an toàn và priority queue theo cận thấp nhất.
4. Thêm **dominance pruning** giữa những node cùng level của ba lô 0/1, chứng minh điều kiện weight/profit cho phép bỏ một node.
5. Thay việc quét phần món chưa quyết định bằng một cấu trúc tính bound nhanh hơn; kiểm tra bound mới không bao giờ dưới optimum brute force của phần còn lại.
6. Thêm giới hạn số node hoặc thời gian chạy, trả **incumbent tốt nhất hiện có và cận tốt nhất của frontier**, đồng thời báo **chưa chứng minh tối ưu** nếu còn node có bound có thể cải thiện.
7. Viết test so sánh DFS/BFS/best-bound trên cây có nhiều món cùng density, món nặng hơn C và C=0; chú ý phân biệt thống kê node với tính đúng optimum.

## 22. Ghi nhớ

Ba chiến lược chọn nhánh trong **branch and bound** đều dựa trên cùng ý tưởng **nút tìm kiếm + cận lạc quan + nghiệm khả thi tốt nhất**:

- **DFS (LIFO):** ưu tiên đi sâu; ít bộ nhớ trên cây nhị phân; thường tìm một nghiệm hoàn chỉnh nhanh nếu chọn nhánh tốt.
- **BFS (FIFO):** mở theo tầng; dễ theo dõi nhưng có thể giữ số nút chờ hàm mũ.
- **Best-bound (priority queue):** với **max** ưu tiên **upperBound cao nhất**, với **min** ưu tiên **lowerBound thấp nhất**; hiệu quả phụ thuộc cận và chi phí heap.
- **Pruning đúng:** với max, bỏ node nếu upperBound≤incumbent; với min, bỏ nếu lowerBound≥bestCost, khi chỉ cần một optimum.
- **Bound không phải incumbent:** bound có thể được tính từ một bài toán nới lỏng không có nghiệm khả thi tương ứng.
- **Fractional knapsack** là cận trên hợp lệ cho bài ba lô 0/1 khi các món được sắp đúng mật độ và chỉ xét các món chưa quyết định.
- **Không có thứ tự tốt nhất phổ quát**: DFS có thể mở ít node hơn best-bound trên bộ này, ngược lại trên bộ khác.
- **Kiểm thử bằng vét cạn** giúp phát hiện bug, nhưng chứng minh an toàn của bound là yếu tố quyết định để giữ bảo đảm tối ưu.

**Câu hỏi thiết kế quan trọng nhất không phải “dùng stack, queue hay heap?” mà là “mình có một bound thật sự an toàn và incumbent khả thi, rồi chính sách chọn nhánh nào cân bằng thời gian tìm nghiệm và bộ nhớ tốt nhất cho cấu trúc bài toán này?”**
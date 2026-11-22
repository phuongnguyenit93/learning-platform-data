# Mô hình hóa đường đi và chi phí trên mạng

Trong các bài toán thuật toán, “mạng” có thể là hệ thống đường bộ, đường bay, viễn thông, chuyển hàng hoặc một lưới trạng thái. **Mô hình hóa đúng** nghĩa là chỉ ra đỉnh, cạnh, hướng, chi phí, trạng thái, điều kiện kết thúc và ràng buộc trước khi chọn thuật toán. Một lời giải Dijkstra cài đúng trên **đồ thị sai** vẫn trả lời sai bài toán thực tế.

Bài **“Mô hình hóa đường đi và chi phí trên mạng”**, nhóm **Thực hành tổng hợp** của Computer Science Algorithms, trình bày quy trình chuyển mô tả thực tế sang đồ thị và chứng minh tính đúng của phép chuyển mô hình. Ví dụ trung tâm: mạng đường một chiều, mỗi cạnh có **chi phí đi lại** và **phí qua trạm**, người đi có thể dùng một phiếu miễn phí trạm ở tối đa một cạnh. Bài phân biệt ba chính sách: **không dùng phiếu, được dùng hoặc không, và bắt buộc dùng đúng một lần**; thiết kế đồ thị trạng thái hai lớp và giải bằng Dijkstra.

Mã Java 17+ độc lập đi kèm dùng `BigInteger` để không tràn số, khôi phục đường đi, kiểm tra từng cạnh và đối chiếu với oracle Bellman–Ford độc lập. Test đã chạy thành công trên **4.096 cấu hình mạng vét cạn**, **600 mạng có seed**, **mạng chuỗi 2.500 đỉnh** cùng các giá trị `Long.MAX_VALUE`.

## 1. Dịch một đề bài thành mô hình

Giả sử đề cho n thành phố và các tuyến đường **một chiều**. Mỗi cạnh u→v có hai thuộc tính không âm: `travel` và `toll`. Tổng chi phí bình thường là `travel+toll`. Người đi có **một** phiếu có thể miễn `toll` của **một lần qua cạnh**, không miễn `travel`. Hỏi chi phí tối thiểu từ s tới t.

Trước khi lập trình cần xác định:

- **Đỉnh V:** một thành phố, từ 0 tới n−1.
- **Cạnh E:** tuyến đường hợp lệ từ `from` tới `to`, có hướng.
- **Trọng số:** giá qua một cạnh bình thường là `travel+toll`.
- **Hành động ưu đãi:** một lần đổi trọng số cạnh thành chỉ `travel`.
- **Lịch sử quan trọng:** còn phiếu hay đã dùng phiếu.
- **Đích hợp lệ:** phụ thuộc yêu cầu có bắt buộc dùng phiếu không.

Nếu đề hỏi đường đi **ngắn nhất theo số chặng**, BFS có thể đủ. Nhưng ở đây chi phí cạnh khác nhau, và trạng thái sử dụng phiếu thay đổi lựa chọn tương lai, nên **BFS trên thành phố đơn thuần không đúng mô hình**.

## 2. Đỉnh nên biểu diễn điều gì?

Một đỉnh không nhất thiết chỉ là địa điểm. Trong đường bộ, đó có thể là ngã tư. Trong mạng tàu, có thể là `(ga,tuyến)` để biểu diễn việc đổi tuyến. Trong bài có nhiên liệu, có thể là `(địa điểm,lượng_xăng_còn)`. Trong bài vé một lần, dùng `(thành_phố,đã_sử_dụng_vé)`.

Quy tắc thiết kế trạng thái: **hai lịch sử có cùng đỉnh chỉ được nhập làm một nếu chúng có các hành động hợp lệ và chi phí tương lai tương đương**. Nếu hai người cùng tới thành phố v nhưng một người đã dùng ưu đãi còn người kia chưa, họ không nhất thiết có cùng chi phí tốt nhất từ v tới t. Không thể chỉ lưu một `dist[v]` và vứt bỏ phần thông tin này.

## 3. Hướng, cạnh song song và self-loop

Một tuyến từ u sang v **không tự tạo** tuyến ngược v sang u. Với đường hai chiều, đề có thể yêu cầu thêm hai cạnh, đôi khi hai chiều có phí khác nhau.

Mạng cũng có thể có **cạnh song song** cùng u→v nhưng khác chi phí. Không được xóa cạnh chỉ vì “đã có tuyến giữa hai đỉnh”: tuyến nhanh nhưng toll cao có thể rất tốt sau khi dùng phiếu, còn tuyến chậm không toll tốt hơn khi chưa có phiếu.

**Self-loop** u→u có thể là chờ hoặc đi một vòng. Trong bài chi phí không âm và phiếu tùy chọn, đi vòng không cần thiết để giảm chi phí; nhưng nếu **bắt buộc dùng phiếu** và s=t, một chu trình có thể tạo đường đi hợp lệ có sử dụng phiếu. Do đó không nên loại self-loop nếu đề chưa cấm.

## 4. Tính cộng được của chi phí và đơn vị đo

Một đường đi gồm các cạnh e1,e2,...,ek, có chi phí thông thường:

~~~text
C(path) = sum_(i=1)^k cost(e_i).
cost(e) = travel(e)+toll(e).
~~~

Chỉ cộng trực tiếp khi `travel` và `toll` được đề cho **cùng đơn vị chi phí**, hoặc có tỷ lệ quy đổi nhất quán. Nếu travel là **phút** và toll là **đồng**, cộng trực tiếp chúng là sai thứ nguyên.

Ví dụ muốn tối ưu **chi phí tổng hợp** có thể định nghĩa `cost = alpha*minutes + money`, trong đó alpha là mức định giá thời gian. Nếu đề muốn **tối thiểu thời gian nhưng phí ≤B**, đó là bài có ràng buộc tài nguyên, không đơn giản là một phép cộng với alpha tùy ý.

Cũng cần phân biệt **chi phí mỗi lần đi qua cạnh** với **chi phí cố định mở tuyến** hoặc giá theo khối lượng. Đường đi ngắn nhất chuẩn chỉ cộng trọng số những cạnh được sử dụng.

## 5. Mạng năm thành phố làm ví dụ

Cho mạng có hướng với nguồn s=0 và đích t=4:

| Cạnh | Travel | Toll | Giá thường |
| --- | ---: | ---: | ---: |
| 0→1 | 3 | 8 | 11 |
| 1→4 | 4 | 1 | 5 |
| 0→2 | 2 | 0 | 2 |
| 2→3 | 2 | 12 | 14 |
| 3→4 | 3 | 1 | 4 |
| 0→4 | 20 | 0 | 20 |
| 1→3 | 2 | 0 | 2 |

Các tuyến không dùng phiếu:

~~~text
0->1->4:       11+5 = 16.
0->1->3->4:    11+2+4 = 17.
0->2->3->4:    2+14+4 = 20.
0->4:          20.
~~~

Vì vậy giá thường tối ưu bằng **16** theo 0→1→4.

Khi dùng phiếu trên cạnh 0→1, giá còn 3+5=**8**. Khi dùng phiếu trên cạnh 2→3, tuyến 0→2→3→4 cũng có giá 2+2+4=**8**. Có nhiều tuyến đồng tối ưu; đáp án chi phí là 8, còn tuyến nào được phục hồi có thể phụ thuộc thứ tự cạnh và cách giải quyết hòa.

## 6. Vì sao tham lam trên tuyến thường ngắn nhất có thể sai?

Chiến lược “tìm đường bình thường rẻ nhất rồi miễn toll lớn nhất trên đó” không luôn tìm ra tối ưu sau phiếu. Phản ví dụ:

~~~text
Tuyến A: bình thường 10, toll lớn nhất 1.
Sau giảm: 9.

Tuyến B: bình thường 12, toll lớn nhất 9.
Sau giảm: 3.
~~~

A thắng khi không ưu đãi, nhưng B thắng khi có ưu đãi. Vì vậy phải **chọn đường và chọn cạnh dùng phiếu đồng thời**, hoặc biến việc sử dụng phiếu thành trạng thái để áp thuật toán đường đi ngắn nhất.

## 7. Đồ thị trạng thái hai lớp

Với mỗi đỉnh v tạo hai đỉnh logic:

~~~text
(v,0): chưa dùng phiếu.
(v,1): đã dùng phiếu.
~~~

Trên mỗi Road u→v, travel=a, toll=b, thêm chuyển tiếp:

~~~text
Không dùng phiếu:
  (u,0) -> (v,0), cost=a+b.
  (u,1) -> (v,1), cost=a+b.

Dùng phiếu:
  (u,0) -> (v,1), cost=a.
~~~

Không tạo đường 1→0 vì đã dùng phiếu không thể lấy lại. Không có chuyển 1→1 giá a vì phiếu không thể dùng hai lần. Mỗi cạnh gốc tạo tối đa 3 cạnh trạng thái, nên số cạnh vẫn O(E), số đỉnh là **2V**.

Có thể mã hóa `state = 2*v+used`; lấy lại `v=state/2`, `used=state%2`. Code kiểm giới hạn số đỉnh để `2*n` không tràn chỉ số int.

## 8. Chính sách kết thúc: FORBIDDEN, OPTIONAL, REQUIRED

Chương trình khai báo:

~~~java
public enum CouponPolicy {
    FORBIDDEN, OPTIONAL, REQUIRED
}
~~~

Xuất phát từ `(s,0)`.

- `FORBIDDEN`: không có cạnh dùng phiếu; chỉ nhận đích `(t,0)`.
- `OPTIONAL`: có thể dùng 0 hoặc 1 phiếu; chọn tối ưu trong `(t,0)` và `(t,1)`.
- `REQUIRED`: phải dùng đúng một phiếu; chỉ nhận `(t,1)`.

Đây là ba **bài toán khác nhau**, dù cùng mạng. Nếu s=t và không có cạnh, `OPTIONAL` trả đường rỗng giá 0, `REQUIRED` báo không có đường hợp lệ. Nếu có chu trình, `REQUIRED` đôi khi có thể đi vòng để dùng phiếu rồi quay lại.

## 9. Đường đi ngắn nhất trên đồ thị mở rộng

Các cạnh trạng thái đều **không âm** vì `travel>=0` và `toll>=0`. Ta có thể chạy **Dijkstra** trên 2V trạng thái:

~~~text
dist[(s,0)] = 0.
dist[các trạng thái khác] = chưa thể tới.
PriorityQueue theo khoảng cách nhỏ nhất.

Khi lấy (u,used) với giá d:
  Với mỗi Road u->v:
    relax((v,used), d+travel+toll).
    Nếu used==0 và được dùng phiếu:
      relax((v,1), d+travel).
~~~

Trong Java, heap lưu các cặp `(state,cost)`. Mỗi khi khoảng cách tốt hơn, thêm một entry mới; nếu một entry cũ được pop nhưng cost không còn bằng dist, bỏ qua. Đây là chiến lược **lazy deletion**, không cần hỗ trợ decrease-key trực tiếp.

## 10. Bất biến chứng minh Dijkstra đúng

Dijkstra dựa trên giả thiết mọi trọng số cạnh không âm: khi trạng thái u được pop với khoảng cách còn hợp lệ nhỏ nhất, không thể có một đường đi rẻ hơn tới u qua các trạng thái chưa được xử lý. Nếu có, tiền tố đầu tiên của đường đó đi vào vùng chưa xử lý sẽ có khoảng cách không lớn hơn chi phí tới u, mâu thuẫn với lựa chọn min-heap.

Vì đồ thị mở rộng biểu diễn **tất cả và chỉ những** bước đi hợp lệ của mô hình có phiếu, khoảng cách Dijkstra tới `(t,used)` là chi phí thấp nhất trong các hành trình kết thúc với đúng trạng thái phiếu ấy.

Nếu cạnh âm, kết luận trên không còn áp dụng: một cạnh có thể làm một trạng thái tưởng đã tối ưu trở nên rẻ hơn sau đó. Vì vậy phần cài đặt chính **từ chối travel/toll âm**; không lách validation để dùng Dijkstra cho mạng hoàn tiền âm.

## 11. Chứng minh tương đương hai mô hình

**Từ hành trình thực sang đường trạng thái:** bắt đầu `(s,0)`. Mỗi Road không dùng phiếu tạo bước `(u,used)->(v,used)` giá `travel+toll`. Lần duy nhất dùng phiếu tạo bước `(u,0)->(v,1)` giá `travel`. Không có lần dùng phiếu thứ hai. Mỗi hành trình hợp lệ ánh xạ thành một đường trong graph trạng thái **bảo toàn tổng chi phí**.

**Từ đường trạng thái về hành trình thực:** từng cạnh trạng thái được tạo từ một Road có thật. Bỏ phần bit `used` ta có hành trình trong mạng gốc. Vì trạng thái không chuyển từ 1 về 0, nhiều nhất một cạnh có giá được miễn toll. Tổng trọng số đường trạng thái đúng bằng tổng chi phí người đi thực trả.

Hai chiều tương ứng này bảo đảm việc tìm đường ngắn nhất đến đích trạng thái theo chính sách là **đúng bài toán gốc**, không chỉ đúng với một mô hình gần giống.

## 12. Truy vết lời giải và kiểm tra đường đi

Không chỉ cần cost; nhiều đề yêu cầu in **lộ trình và vị trí dùng phiếu**. Khi relax tốt hơn, code lưu `Parent` gồm trạng thái trước, Road gốc và cờ `waived`. Sau khi chọn trạng thái đích, lần ngược Parent tới `(s,0)`, đảo danh sách để ra các `Leg`.

Một `Route` chứa:

~~~text
cost: BigInteger.
couponUsed: true/false.
legs: danh sách các đoạn từ source tới target.
~~~

Kiểm thử của code xác minh tất cả leg liên tục, Road thực sự tồn tại, mỗi leg tính đúng travel/toll, phiếu xuất hiện tối đa một lần, điều kiện FORBIDDEN/REQUIRED được giữ, và tính lại tổng BigInteger bằng cost in ra.

Một chi phí đúng không có nghĩa đường được in ra đúng. **Kiểm tra đường đi độc lập** là bước cần thiết khi lời giải yêu cầu truy vết.

## 13. Cạnh song song, bằng chi phí và vòng 0

Có thể có nhiều Road cùng u,v. Cần giữ riêng vì toll và travel khác nhau; sau phiếu, thứ tự lựa chọn có thể đảo.

Cạnh giá 0 và chu trình giá 0 cũng hợp lệ. Code chỉ cập nhật parent khi ứng viên có giá **nhỏ hơn** dist hiện có, không cập nhật khi bằng nhau. Điều này tránh đảo parent liên tục trên các chu trình 0 và giúp kết quả truy vết ổn định.

Khi nhiều hành trình cùng rẻ nhất, đề thường chấp nhận bất kỳ tuyến nào. Nếu đề yêu cầu **ít cạnh nhất trong những tuyến đồng chi phí**, phải mở rộng tiêu chí so sánh (ví dụ cặp `(cost,edgeCount)`) và chứng minh thuật toán mới theo thứ tự lexicographic. Không thể mặc nhiên cho rằng Dijkstra hiện tại chọn ít cạnh nhất.

## 14. BigInteger và tràn số chi phí

Hai long không âm có thể cộng thành một số vượt Long.MAX_VALUE. Khi `travel=Long.MAX_VALUE`, `toll=Long.MAX_VALUE`, cộng long thô sẽ overflow; trong Dijkstra, một cost âm giả làm hỏng mọi giả thiết.

Bản Java chuyển từng thành phần sang **BigInteger trước khi cộng**. Khoảng cách là `BigInteger[]`, phần tử `null` nghĩa là chưa thể đến. Không sử dụng sentinel `INF=Long.MAX_VALUE` vì một đường đi có thể có **chi phí đúng bằng** giá trị đó.

~~~text
Road duy nhất:
travel=9223372036854775807.
toll=9223372036854775807.

Giá không phiếu:
18446744073709551614.

Giá khi miễn toll:
9223372036854775807.
~~~

Chương trình chạy và tính chính xác cả hai. Với mạng lớn, BigInteger có overhead về bit arithmetic/heap; nếu đề bảo đảm mọi phép cộng an toàn trong long, có thể dùng long với `Math.addExact` hoặc kiểm giới hạn nhưng phải công bố chính sách overflow.

## 15. Không liên thông và nguồn bằng đích

Một truy vấn **không tới được** trả `Optional.empty()`; không trả 0 vì 0 là một chi phí hợp lệ (đường rỗng hoặc đường giá 0). Trường hợp source=target, FORBIDDEN/OPTIONAL có đường rỗng giá 0, còn REQUIRED chỉ hợp lệ khi có một đường đi có dùng phiếu quay lại đích.

Bản test bao phủ mạng rỗng, đỉnh đơn, cạnh một chiều, self-loop, cạnh trùng và s=t. Đây là các trường hợp rất dễ làm lộ lỗi mô hình trạng thái hoặc điều kiện kết thúc.

## 16. Bellman–Ford khi có trọng số âm

Nếu network có cạnh âm, **Dijkstra tiêu chuẩn** không có bảo đảm đúng. Khi không có chu trình âm ảnh hưởng tới đích, Bellman–Ford có thể tìm shortest path bằng cách relax toàn bộ cạnh nhiều lượt.

Nếu có V' đỉnh, thực hiện tối đa V'−1 lượt; một lượt tiếp theo phát hiện cạnh vẫn giảm được khoảng cách, báo có chu trình âm reachable. Nếu chu trình âm reachable từ nguồn **và có thể tới đích**, có thể lặp lại để làm giá đi xuống âm vô hạn theo mô hình được phép lặp cạnh, nên không tồn tại optimum hữu hạn.

Oracle trong Java dùng **Bellman–Ford độc lập** trên đồ thị hai lớp nhưng test vẫn giới hạn trọng số **không âm**. Oracle này là công cụ kiểm tính đúng của Dijkstra, không phải lời hứa hỗ trợ chi phí âm trong API chính.

## 17. Phân biệt BFS, 0–1 BFS, Dijkstra và DAG

| Điều kiện trọng số/cấu trúc | Thuật toán thường phù hợp |
| --- | --- |
| Mỗi cạnh tính đúng 1 chặng | BFS |
| Trọng số chỉ 0 hoặc 1 | 0–1 BFS |
| Trọng số không âm | Dijkstra |
| DAG, kể cả cạnh âm | Shortest path theo thứ tự topo |
| Có cạnh âm, không có chu trình âm reachable ảnh hưởng đích | Bellman–Ford hoặc biến thể phù hợp |
| Mạng có sức chứa và cần chuyển nhiều đơn vị hàng | Flow / min-cost flow, không phải shortest path đơn thuần |

Chọn thuật toán **sau khi đã xây mô hình**. Một bài về “mạng giao thông” có thể là shortest path, max flow, min-cost flow, định tuyến đa mục tiêu hoặc lập lịch, tùy câu hỏi chính xác.

## 18. Đường đi so với luồng mạng

Shortest path tìm **một hành trình**, chi phí cộng theo từng cạnh. Flow xem **lượng hàng/tín hiệu** đi qua các cạnh với capacity và bảo toàn lưu lượng tại đỉnh trung gian.

Ví dụ cạnh u→v có giá 2 đồng/kiện và sức chứa 5 kiện. Tìm tuyến tốt nhất cho một kiện có thể dùng trọng số 2. Nhưng gửi 100 kiện không thể chỉ nhân chi phí đường rẻ nhất với 100 khi một cạnh sức chứa 5; bài cần **min-cost flow**.

Không nhầm `edge cost` với `capacity`, `flow` hay `fixed charge`. Bản Java chỉ mô hình hóa chi phí của một tuyến, không quản lý luồng hàng và giới hạn sức chứa.

## 19. Mạng đa tiêu chí và ngân sách

Nếu đề nói “tối thiểu thời gian với phí không vượt B”, một trọng số duy nhất `time+toll` thường không giải được. Có thể mở rộng thành `(v,budgetUsed)`, duy trì nhiều nhãn Pareto `(time,cost)` hoặc dùng một thuật toán constrained shortest path riêng.

Nếu đề nói “ưu tiên ít thời gian nhất, nếu hòa thì ít phí nhất”, có thể tối ưu lexicographic `(time,toll)` với quy tắc cộng và so phù hợp. Nếu đề yêu cầu **không quá k chặng**, thêm số chặng vào trạng thái.

Cần phân biệt chính xác các từ “tối đa”, “ít nhất” và “đúng bằng”. Sai một dấu điều kiện thường khiến thuật toán giải sai ngay cả khi dist được tính hợp lý.

## 20. Mạng phụ thuộc thời gian

Nhiều mạng thực tế có travel time phụ thuộc giờ xuất phát hoặc phải chờ chuyến:

~~~text
arrival = departure + travelTime(edge,departure).
~~~

Dijkstra với **trọng số tĩnh** không đủ cho dạng này. Cần mô hình time-expanded graph `(station,time)` hoặc time-dependent shortest path; giả thiết **FIFO** thường quan trọng để bảo đảm xuất phát muộn hơn trên một cạnh không đến sớm hơn nếu không có quyền chờ được tính khác.

Ví dụ một chuyến tàu chạy lúc 09:00 và 10:00; người đến ga lúc 09:01 phải chờ gần một giờ, không thể dùng một cạnh luôn có cost=10 phút rồi coi kết quả đúng. Bản Java của bài chỉ xử lý mạng **tĩnh, không có thời gian chờ**.

## 21. Mở rộng trạng thái cho ràng buộc khác

Tư duy `(vertex,couponUsed)` áp dụng cho:

- Được dùng tối đa k vé: `(v,usedCount)` có k+1 lớp.
- Có tối đa k chìa khóa khác nhau: `(v,keyMask)` có thể tới 2^k trạng thái.
- Phải ghé một số điểm: `(v,visitedMask)`.
- Tàu có nhiều loại tuyến: `(station,line)`.
- Nhiên liệu hữu hạn: `(v,fuelRemaining)`.
- Đã hoàn thành một bước nhiệm vụ: `(v,phase)`.

Mỗi chiều trạng thái có chi phí thời gian/bộ nhớ. Trước khi thêm bitmask, cần ước lượng `V * 2^k`; nếu k lớn, phương án có thể bùng nổ. Cũng phải chứng minh các chuyển tiếp mô tả **đủ và chỉ** những hành động hợp lệ.

## 22. Độ phức tạp của mô hình hai lớp

Nếu mạng gốc có V đỉnh và E cạnh:

~~~text
V' = 2V.
E' <= 3E.

Dijkstra với heap lazy:
  O((V'+E') log(V'+E'+1))
  phép so/cập nhật heap.

Gọn hơn:
  O((V+E) log(V+E+1)).
~~~

Bộ nhớ adjacency + dist/parent + heap là O(V+E) theo số object ở mô hình lý thuyết, chưa tính độ dài bit của BigInteger.

Oracle Bellman–Ford trên V'≈2V và E'≈3E thường O(V·E); chỉ dùng test nhỏ. Với BigInteger, chi phí thực tế mỗi phép cộng/so phụ thuộc độ dài bit, nhưng về số thao tác heap/relax vẫn như trên.

## 23. Chi tiết chương trình Java và hợp đồng API

Đây là một chương trình **Java 17+ tự chứa**:

- `Road`: cạnh có hướng, travel/toll long không âm.
- `Network`: adjacency list; từ chối đỉnh ngoài miền, travel/toll âm, số đỉnh không hợp lệ.
- `CouponPolicy`: ba chế độ phiếu.
- `StateCost`: entry heap theo BigInteger cost và state.
- `Parent`, `Leg`: phục hồi đường và hành động waived.
- `Route`: kết quả có `cost`, `couponUsed`, `legs`.
- `cheapest`: Dijkstra trên 2V trạng thái; trả Optional.empty nếu không có hành trình đúng chính sách.
- `oracle`: Bellman–Ford độc lập cho kiểm thử.
- `verifyRoute`: đối chiếu từng leg với mạng gốc và tính lại tổng.
- `verify`: các test exhaustive/random/stress/invalid.

Đây là mã xử lý **đường đi có phiếu**, không phải một framework mọi loại mạng. Các chi phí tĩnh, phiếu miễn toll của một lần đi qua cạnh và mọi trọng số không âm là **giả thiết bắt buộc**.

## 24. Java 17+ hoàn chỉnh

Lưu mã sau thành **NetworkPathCostModel.java**. Biên dịch/chạy không cần thư viện ngoài.

~~~java
import java.math.BigInteger;
import java.util.*;

public final class NetworkPathCostModel {
    private NetworkPathCostModel() { }

    public enum CouponPolicy { FORBIDDEN, OPTIONAL, REQUIRED }

    public record Road(int from, int to, long travel, long toll) { }
    public record Leg(int from, int to, long travel,
                      long toll, boolean waived) { }
    public record Route(BigInteger cost,
                        boolean couponUsed, List<Leg> legs) { }

    public static final class Network {
        private final List<Road>[] outgoing;

        @SuppressWarnings("unchecked")
        public Network(int vertices) {
            if (vertices <= 0 || vertices > Integer.MAX_VALUE / 2) {
                throw new IllegalArgumentException("invalid vertex count");
            }
            outgoing = (List<Road>[]) new List<?>[vertices];
            for (int i = 0; i < vertices; i++) {
                outgoing[i] = new ArrayList<>();
            }
        }

        public int vertices() { return outgoing.length; }

        public void addRoad(int from, int to, long travel, long toll) {
            if (from < 0 || from >= vertices()
                    || to < 0 || to >= vertices()
                    || travel < 0 || toll < 0) {
                throw new IllegalArgumentException("invalid directed road");
            }
            outgoing[from].add(new Road(from,to,travel,toll));
        }

        public List<Road> outgoing(int vertex) {
            return Collections.unmodifiableList(outgoing[vertex]);
        }
    }

    private record StateCost(int state, BigInteger cost) { }
    private record Parent(int previousState, Road road, boolean waived) { }

    private static BigInteger normalCost(Road r) {
        return BigInteger.valueOf(r.travel())
                .add(BigInteger.valueOf(r.toll()));
    }

    private static void relax(int next, BigInteger candidate,
                              int parentState, Road road, boolean waived,
                              BigInteger[] distance, Parent[] parents,
                              PriorityQueue<StateCost> queue) {
        if (distance[next] == null
                || candidate.compareTo(distance[next]) < 0) {
            distance[next] = candidate;
            parents[next] = new Parent(parentState,road,waived);
            queue.add(new StateCost(next,candidate));
        }
    }

    public static Optional<Route> cheapest(Network network,
                                           int source, int target,
                                           CouponPolicy policy) {
        if (network == null || policy == null) {
            throw new IllegalArgumentException("null network or policy");
        }
        int n = network.vertices();
        if (source < 0 || source >= n || target < 0 || target >= n) {
            throw new IllegalArgumentException("invalid vertex");
        }

        BigInteger[] distance = new BigInteger[2*n];
        Parent[] parents = new Parent[2*n];
        PriorityQueue<StateCost> queue = new PriorityQueue<>(
                Comparator.comparing(StateCost::cost)
                          .thenComparingInt(StateCost::state));
        int initial = 2*source;
        distance[initial] = BigInteger.ZERO;
        queue.add(new StateCost(initial,BigInteger.ZERO));

        while (!queue.isEmpty()) {
            StateCost current = queue.remove();
            if (!current.cost().equals(distance[current.state()])) {
                continue;
            }
            int vertex = current.state()/2;
            int used = current.state()%2;
            for (Road road : network.outgoing(vertex)) {
                int next = 2*road.to()+used;
                BigInteger paid = current.cost().add(normalCost(road));
                relax(next,paid,current.state(),road,false,
                        distance,parents,queue);
                if (used == 0 && policy != CouponPolicy.FORBIDDEN) {
                    int spentState = 2*road.to()+1;
                    BigInteger discounted = current.cost().add(
                            BigInteger.valueOf(road.travel()));
                    relax(spentState,discounted,current.state(),road,true,
                            distance,parents,queue);
                }
            }
        }

        int plain = 2*target, spent = plain+1;
        int chosen;
        if (policy == CouponPolicy.FORBIDDEN) {
            chosen = plain;
        } else if (policy == CouponPolicy.REQUIRED) {
            chosen = spent;
        } else if (distance[plain] == null) {
            chosen = spent;
        } else if (distance[spent] != null
                && distance[spent].compareTo(distance[plain]) < 0) {
            chosen = spent;
        } else {
            chosen = plain;
        }

        if (distance[chosen] == null) return Optional.empty();
        ArrayList<Leg> reversed = new ArrayList<>();
        int cursor = chosen;
        while (cursor != initial) {
            Parent p = parents[cursor];
            if (p == null) throw new AssertionError("broken predecessor");
            Road r = p.road();
            reversed.add(new Leg(r.from(),r.to(),
                    r.travel(),r.toll(),p.waived()));
            cursor = p.previousState();
        }
        Collections.reverse(reversed);
        return Optional.of(new Route(distance[chosen],
                chosen % 2 == 1,List.copyOf(reversed)));
    }

    // Independent Bellman-Ford oracle on the explicitly expanded graph.
    private static Optional<BigInteger> oracle(Network network,
                                               int source, int target,
                                               CouponPolicy policy) {
        int n = network.vertices();
        BigInteger[] dist = new BigInteger[2*n];
        dist[2*source] = BigInteger.ZERO;
        for (int iteration = 0; iteration < 2*n-1; iteration++) {
            boolean updated = false;
            for (int vertex = 0; vertex < n; vertex++) {
                for (int used = 0; used < 2; used++) {
                    int state = 2*vertex+used;
                    if (dist[state] == null) continue;
                    for (Road road : network.outgoing(vertex)) {
                        int next = 2*road.to()+used;
                        BigInteger candidate = dist[state].add(
                                BigInteger.valueOf(road.travel()))
                                .add(BigInteger.valueOf(road.toll()));
                        if (dist[next] == null
                                || candidate.compareTo(dist[next]) < 0) {
                            dist[next] = candidate;
                            updated = true;
                        }
                        if (used == 0 && policy != CouponPolicy.FORBIDDEN) {
                            next = 2*road.to()+1;
                            candidate = dist[state].add(
                                    BigInteger.valueOf(road.travel()));
                            if (dist[next] == null
                                    || candidate.compareTo(dist[next]) < 0) {
                                dist[next] = candidate;
                                updated = true;
                            }
                        }
                    }
                }
            }
            if (!updated) break;
        }
        BigInteger normal = dist[2*target];
        BigInteger spent = dist[2*target+1];
        if (policy == CouponPolicy.FORBIDDEN) {
            return Optional.ofNullable(normal);
        }
        if (policy == CouponPolicy.REQUIRED) {
            return Optional.ofNullable(spent);
        }
        if (normal == null) return Optional.ofNullable(spent);
        if (spent == null) return Optional.of(normal);
        return Optional.of(normal.min(spent));
    }

    private static void verifyRoute(Network g, int source, int target,
                                    CouponPolicy policy, Route route) {
        int vertex = source, couponCount = 0;
        BigInteger cost = BigInteger.ZERO;
        for (Leg leg : route.legs()) {
            if (leg.from() != vertex) {
                throw new AssertionError("noncontiguous route");
            }
            boolean exists = false;
            for (Road road : g.outgoing(vertex)) {
                if (road.to() == leg.to()
                        && road.travel() == leg.travel()
                        && road.toll() == leg.toll()) {
                    exists = true;
                    break;
                }
            }
            if (!exists) throw new AssertionError("invented road");
            if (leg.waived()) couponCount++;
            if (couponCount > 1) {
                throw new AssertionError("coupon used twice");
            }
            cost = cost.add(BigInteger.valueOf(leg.travel()));
            if (!leg.waived()) {
                cost = cost.add(BigInteger.valueOf(leg.toll()));
            }
            vertex = leg.to();
        }
        if (vertex != target || !cost.equals(route.cost())
                || route.couponUsed() != (couponCount == 1)) {
            throw new AssertionError("invalid reconstructed route");
        }
        if (policy == CouponPolicy.FORBIDDEN && couponCount != 0
                || policy == CouponPolicy.REQUIRED && couponCount != 1) {
            throw new AssertionError("coupon policy violation");
        }
    }

    private static void testCase(Network g, int source, int target) {
        for (CouponPolicy p : CouponPolicy.values()) {
            Optional<Route> fast = cheapest(g,source,target,p);
            Optional<BigInteger> slow = oracle(g,source,target,p);
            if (fast.isPresent() != slow.isPresent()) {
                throw new AssertionError("reachability differs");
            }
            if (fast.isPresent()) {
                if (!fast.get().cost().equals(slow.get())) {
                    throw new AssertionError("minimum cost differs");
                }
                verifyRoute(g,source,target,p,fast.get());
            }
        }
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("invalid input accepted");
    }

    public static void verify() {
        int exhaustive = 0;
        for (int code = 0; code < 4096; code++) {
            Network g = new Network(3);
            int mask = code;
            for (int from = 0; from < 3; from++) {
                for (int to = 0; to < 3; to++) {
                    if (from == to) continue;
                    int type = mask % 4;
                    mask /= 4;
                    if (type == 1) g.addRoad(from,to,0,0);
                    else if (type == 2) g.addRoad(from,to,1,0);
                    else if (type == 3) g.addRoad(from,to,1,2);
                }
            }
            for (int source = 0; source < 3; source++) {
                for (int target = 0; target < 3; target++) {
                    testCase(g,source,target);
                }
            }
            exhaustive++;
        }

        Random rng = new Random(5552026L);
        long[] costs = {0,1,2,17,9007199254740993L,
                        Long.MAX_VALUE};
        int randomCases = 0;
        for (int test = 0; test < 600; test++) {
            int n = 1+rng.nextInt(7);
            Network g = new Network(n);
            int edges = rng.nextInt(21);
            for (int i = 0; i < edges; i++) {
                g.addRoad(rng.nextInt(n),rng.nextInt(n),
                        costs[rng.nextInt(costs.length)],
                        costs[rng.nextInt(costs.length)]);
            }
            for (int k = 0; k < 3; k++) {
                testCase(g,rng.nextInt(n),rng.nextInt(n));
            }
            randomCases++;
        }

        Network chain = new Network(2500);
        for (int i = 0; i < 2499; i++) {
            chain.addRoad(i,i+1,2,7);
        }
        BigInteger full = BigInteger.valueOf(2499L*9);
        BigInteger discount = full.subtract(BigInteger.valueOf(7));
        Optional<Route> normal = cheapest(
                chain,0,2499,CouponPolicy.FORBIDDEN);
        Optional<Route> optional = cheapest(
                chain,0,2499,CouponPolicy.OPTIONAL);
        Optional<Route> required = cheapest(
                chain,0,2499,CouponPolicy.REQUIRED);
        if (normal.isEmpty() || optional.isEmpty() || required.isEmpty()
                || !normal.get().cost().equals(full)
                || !optional.get().cost().equals(discount)
                || !required.get().cost().equals(discount)
                || optional.get().legs().size() != 2499) {
            throw new AssertionError("large chain test failed");
        }

        Network huge = new Network(2);
        huge.addRoad(0,1,Long.MAX_VALUE,Long.MAX_VALUE);
        BigInteger expectedFull = BigInteger.valueOf(Long.MAX_VALUE)
                .multiply(BigInteger.TWO);
        if (!cheapest(huge,0,1,CouponPolicy.FORBIDDEN)
                .orElseThrow().cost().equals(expectedFull)
                || !cheapest(huge,0,1,CouponPolicy.OPTIONAL)
                .orElseThrow().cost()
                .equals(BigInteger.valueOf(Long.MAX_VALUE))) {
            throw new AssertionError("BigInteger overflow guard failed");
        }

        Network blank = new Network(2);
        if (cheapest(blank,0,1,CouponPolicy.OPTIONAL).isPresent()
                || cheapest(blank,0,0,CouponPolicy.REQUIRED).isPresent()
                || cheapest(blank,0,0,CouponPolicy.OPTIONAL)
                   .orElseThrow().cost().signum() != 0) {
            throw new AssertionError("empty/start-is-target failed");
        }
        expectInvalid(() -> new Network(0));
        expectInvalid(() -> new Network(-2));
        expectInvalid(() -> huge.addRoad(-1,1,1,1));
        expectInvalid(() -> huge.addRoad(0,2,1,1));
        expectInvalid(() -> huge.addRoad(0,1,-1,0));
        expectInvalid(() -> huge.addRoad(0,1,0,-1));
        expectInvalid(() -> cheapest(huge,0,2,CouponPolicy.OPTIONAL));
        expectInvalid(() -> cheapest(null,0,1,CouponPolicy.OPTIONAL));
        expectInvalid(() -> cheapest(huge,0,1,null));

        System.out.println("Exhaustive directed networks: "
                +exhaustive+" PASS");
        System.out.println("Seeded weighted networks: "
                +randomCases+" PASS");
        System.out.println("Long chain n=2500: PASS");
        System.out.println("Policies, paths, huge costs and invalid inputs: PASS");
    }

    public static void main(String[] args) {
        Network example = new Network(5);
        example.addRoad(0,1,3,8);
        example.addRoad(1,4,4,1);
        example.addRoad(0,2,2,0);
        example.addRoad(2,3,2,12);
        example.addRoad(3,4,3,1);
        example.addRoad(0,4,20,0);
        example.addRoad(1,3,2,0);
        System.out.println("Normal route cost: "
                +cheapest(example,0,4,CouponPolicy.FORBIDDEN)
                .orElseThrow().cost());
        Route best = cheapest(example,0,4,CouponPolicy.OPTIONAL)
                .orElseThrow();
        System.out.println("Optional coupon cost: "+best.cost());
        System.out.println("Required coupon cost: "
                +cheapest(example,0,4,CouponPolicy.REQUIRED)
                .orElseThrow().cost());
        System.out.println("Coupon used: "+best.couponUsed());
        System.out.println("Route vertices: "+routeVertices(0,best.legs()));
        System.out.println("Source equals target (optional): "
                +cheapest(example,2,2,CouponPolicy.OPTIONAL)
                .orElseThrow().cost());

        Network huge = new Network(2);
        huge.addRoad(0,1,Long.MAX_VALUE,Long.MAX_VALUE);
        System.out.println("Huge normal cost: "
                +cheapest(huge,0,1,CouponPolicy.FORBIDDEN)
                .orElseThrow().cost());
        System.out.println("Huge optional coupon cost: "
                +cheapest(huge,0,1,CouponPolicy.OPTIONAL)
                .orElseThrow().cost());
        verify();
    }

    private static List<Integer> routeVertices(int source,
                                               List<Leg> legs) {
        ArrayList<Integer> vertices = new ArrayList<>();
        vertices.add(source);
        for (Leg leg : legs) vertices.add(leg.to());
        return vertices;
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac NetworkPathCostModel.java
java NetworkPathCostModel
~~~

**Stdout chính xác quan sát được từ lần chạy Java:**

~~~text
Normal route cost: 16
Optional coupon cost: 8
Required coupon cost: 8
Coupon used: true
Route vertices: [0, 1, 4]
Source equals target (optional): 0
Huge normal cost: 18446744073709551614
Huge optional coupon cost: 9223372036854775807
Exhaustive directed networks: 4096 PASS
Seeded weighted networks: 600 PASS
Long chain n=2500: PASS
Policies, paths, huge costs and invalid inputs: PASS
~~~

Với ví dụ có nhiều tuyến đồng hạng, cùng một cost=8 vẫn có thể ứng với đường khác nếu thay đổi thứ tự các cạnh/cách phá hòa. Bản code này in `[0,1,4]`. Trong công cụ JShell kiểm thử xuất hiện diagnostic BOM khi khởi động shell, nhưng chương trình thực thi đã in đủ stdout và vượt qua mọi assertion.

## 25. Kiểm thử vét cạn 4.096 mạng

Mạng ba đỉnh có 3×2=6 cặp cạnh có hướng giữa hai đỉnh phân biệt. Với mỗi cặp, chọn một trong bốn loại:

~~~text
0: vắng cạnh.
1: travel=0, toll=0.
2: travel=1, toll=0.
3: travel=1, toll=2.
~~~

Tổng cộng `4^6 = 4096` cấu hình. Với từng cấu hình, kiểm mọi lựa chọn 3 nguồn ×3 đích ×3 chính sách:

~~~text
4096 * 3 * 3 * 3 = 110592
lần so sánh Dijkstra với oracle Bellman–Ford.
~~~

Oracle không dùng heap và mỗi kết quả còn được kiểm có đường đi hợp lệ. Kết quả: **4.096 mạng PASS**. Các trường hợp có cạnh 0, chu trình, không liên thông và nguồn trùng đích đều xuất hiện.

## 26. Kiểm thử 600 mạng ngẫu nhiên và chuỗi dài

Bộ thứ hai dùng `Random(5552026L)`, sinh 600 mạng có 1..7 đỉnh và 0..20 cạnh, cho phép self-loop và cạnh song song. Giá travel/toll chọn từ:

~~~text
0, 1, 2, 17,
9007199254740993, Long.MAX_VALUE.
~~~

Mỗi mạng được kiểm ở ba cặp nguồn/đích ngẫu nhiên, đủ ba chính sách, đối chiếu BigInteger Bellman–Ford và kiểm route. Kết quả **600 mạng PASS**.

Một mạng chuỗi dài **2.500 đỉnh**, mỗi cạnh từ i tới i+1 có travel=2,toll=7. Đường từ 0 tới 2499 cần 2499 leg:

~~~text
Không phiếu: 2499*9 = 22491.
Một phiếu:   22491-7 = 22484.
~~~

Code kiểm FORBIDDEN 22491, OPTIONAL/REQUIRED 22484 và đủ 2499 leg; kết quả **PASS**. Cạnh chi phí cực đại được kiểm để bảo đảm không overflow và không nhầm unreachable.

## 27. Vì sao oracle độc lập quan trọng?

Chạy cùng một hàm Dijkstra hai lần không phải kiểm chứng độc lập. Bản Java dùng **Bellman–Ford** làm oracle, relax các chuyển tiếp trên hai lớp theo lượt, không dùng PriorityQueue hay Parent của Dijkstra.

Với mỗi query:

~~~text
Reachable/unreachable phải trùng.
Nếu reachable, BigInteger total cost phải trùng.
Đường đi phải liên tục, đủ Road thực tế.
Số lần waived phải đúng chính sách.
Tổng tính lại từ Leg phải bằng total cost.
~~~

Bộ test dùng input nhỏ để oracle chậm vẫn chạy được. Bài không gọi oracle trên chuỗi 2.500 đỉnh để tránh O(V·E) không cần thiết; thay vào đó chuỗi có đáp án **tính tay bằng công thức**, độc lập với Dijkstra.

## 28. Lỗi thường gặp trong mô hình hóa

1. Tự coi đường một chiều là hai chiều.
2. Dùng BFS khi các cạnh có trọng số không bằng nhau.
3. Cộng đại lượng khác đơn vị mà không quy đổi.
4. Miễn cả travel và toll dù phiếu chỉ miễn toll.
5. Dùng ưu đãi nhiều hơn một lần.
6. Chỉ giữ `dist[v]`, mất bit trạng thái.
7. Tìm tuyến không phiếu tốt nhất rồi mới áp ưu đãi, bỏ lỡ tuyến khác.
8. Nhầm OPTIONAL với REQUIRED khi chọn đích.
9. Cho chuyển used=1 về used=0, phục hồi phiếu đã tiêu.
10. Xóa cạnh song song có cùng hai đỉnh.
11. Tự cấm self-loop khi đề không cấm.
12. Dùng Dijkstra cho trọng số âm.
13. Không xét ảnh hưởng của chu trình âm trong mạng hoàn tiền.
14. Cộng long overflow rồi xem kết quả âm là chi phí hợp lệ.
15. Dùng `INF` làm sentinel trùng chi phí hợp lệ.
16. Dùng `Optional.empty` và giá 0 thay nhau.
17. Quên s=t và hành trình rỗng.
18. Chỉ so cost mà không kiểm đường đi.
19. Cập nhật Parent khi chi phí bằng nhau trên chu trình giá 0.
20. Khẳng định một tuyến duy nhất khi nhiều tuyến cùng tối ưu.
21. Dùng comparator bằng phép trừ có thể overflow.
22. Nhầm shortest path với min-cost flow có capacity.
23. Coi chi phí theo thời gian là hằng số.
24. Thêm bitmask trạng thái nhưng không ước lượng memory.
25. Dùng Oracle cùng mã nguồn thuật toán chính, có thể cùng lỗi.
26. Không test số đỉnh 1, mạng rỗng, cực trị long.
27. Tự kết luận Dijkstra O(E log V) đủ mô tả bit-cost BigInteger.
28. Trộn thứ tự phá hòa vào yêu cầu tối ưu mà đề không nói.
29. Bỏ qua việc phí/travel có thể bằng 0.
30. Không kiểm input âm/trạng thái phiếu null.
31. Quên rằng “ít chặng nhất” khác “chi phí ít nhất”.
32. Không tách việc **tìm đường** và **tìm lượng flow trên mạng**.

## 29. Bài tập tự luyện

**Bài 1:** Với mạng ví dụ, tính tay giá thường của 0→1→4, 0→1→3→4, 0→2→3→4 và 0→4.

**Bài 2:** Nếu được miễn toll đúng một lần, tuyến nào có giá 8? Vì sao có hai lời giải đồng tối ưu?

**Bài 3:** Vẽ graph hai lớp cho hai đỉnh với một Road travel=3,toll=5. Liệt kê ba cạnh chuyển trạng thái.

**Bài 4:** Chứng minh hai chiều tương đương giữa hành trình có phiếu và đường trạng thái.

**Bài 5:** Xét s=t, mạng không có cạnh và policy REQUIRED. Tại sao không được trả đường rỗng giá 0?

**Bài 6:** Thêm self-loop phí 0, xem kết quả REQUIRED với s=t thay đổi thế nào.

**Bài 7:** Tạo phản ví dụ chiến lược chọn phiếu trên đường thường tối ưu.

**Bài 8:** Mô hình hóa hai loại phiếu dùng tối đa một lần bằng mask, đếm số trạng thái.

**Bài 9:** Với `Long.MAX_VALUE` ở travel và toll, tính tổng BigInteger khi có/không có phiếu.

**Bài 10:** Thử mạng có cạnh ngược không tồn tại và test reachability.

**Bài 11:** Dùng Bellman–Ford độc lập để so mọi cấu hình ba đỉnh và chính sách.

**Bài 12:** Đề yêu cầu thời gian tối thiểu nhưng toll≤B: giải thích vì sao một trọng số tổng đơn thuần có thể sai.

**Bài 13:** Một đường có sức chứa 5 và phí 2/kiện. Vì sao gửi 100 kiện phải dùng mô hình flow?

**Bài 14:** Thiết kế time-expanded graph cho tuyến tàu chạy theo giờ và thời gian chờ.

**Bài 15:** Thêm tiêu chí ít chặng nhất khi cost bằng nhau; đổi trạng thái/distance hoặc quy tắc so sánh phù hợp.

**Bài 16:** Xây 600 mạng random có seed, kiểm cost/path với một oracle khác Dijkstra.

## 30. Checklist chọn mô hình và thuật toán

Trước khi code, tự hỏi:

- Đỉnh và cạnh biểu diễn đúng đối tượng nào?
- Cạnh có hướng? Có song song/self-loop?
- Chi phí cùng đơn vị và có tính cộng theo đường đi?
- Có tài nguyên/vé/điều kiện đã thực hiện cần đưa vào state?
- Trọng số của **đồ thị thực sự chạy thuật toán** có không âm?
- Đích hợp lệ là lớp nào? “Tối đa” khác “đúng một lần”?
- Cần đường hay chỉ cần cost? Đã kiểm predecessor và Road chưa?
- Tổng chi phí có vượt long? Sentinel unreachable có an toàn?
- Bài hỏi shortest path, constrained path, min-cost flow hay multi-objective?
- Có test độc lập đối với không liên thông, chu trình 0, biên lớn và đường đồng hạng?

**Kết luận:** Mô hình hóa đường đi và chi phí trên mạng là nghệ thuật đưa đúng **quyền lựa chọn, chi phí và ràng buộc** vào cấu trúc đồ thị. Với quyền miễn toll đúng một lần, đồ thị hai lớp tạo ra bài đường đi ngắn nhất không âm; Dijkstra giải nhanh, BigInteger bảo toàn chi phí lớn và một oracle Bellman–Ford độc lập giúp kiểm chứng cả nghiệm tối ưu lẫn lộ trình. Bài học có thể áp dụng cho vé, nhiên liệu, trạm bắt buộc, nhiều tuyến tàu và nhiều ràng buộc khác — miễn là chứng minh lại phép chuyển trạng thái cho đúng đề.

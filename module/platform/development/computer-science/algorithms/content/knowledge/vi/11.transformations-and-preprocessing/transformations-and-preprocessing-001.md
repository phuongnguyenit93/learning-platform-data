# Biến bài toán về một bài toán đã biết cách giải

Khi gặp một đề thuật toán mới, đôi khi phần khó nhất không phải viết một thuật toán hoàn toàn mới, mà là **nhận ra cấu trúc đã quen** ẩn sau cách diễn đạt của đề. Ta có thể chuyển đầu vào hoặc cách nhìn về bài toán sang một biểu diễn khác, giải bằng một phương pháp đã hiểu và kiểm chứng, rồi chuyển kết quả trở lại đúng thứ đề gốc yêu cầu.

Cách tiếp cận này gọi là **biến đổi bài toán** hoặc **quy giảm về bài toán đã biết (reduction)**. Trong chương **Biến đổi và tiền xử lý** của Computer Science Algorithms, kỹ năng quan trọng không phải thuộc nhiều “mẹo”, mà là biết thiết lập một ánh xạ giữ nguyên đáp án, kiểm tra tiền điều kiện và tính đủ cả chi phí biến đổi lẫn chi phí giải.

Bài học sẽ đi từ khuôn thiết kế tổng quát tới hai ví dụ đủ sâu: **tổng của đoạn liên tiếp → hiệu của hai tổng tiền tố → tra cứu bằng HashMap**, và **số phòng họp tối thiểu → số khoảng đồng thời lớn nhất → quét mốc thời gian đã sắp xếp**. Cả hai có chương trình Java 17+ và bộ kiểm thử vét cạn độc lập.

## 1. Thế nào là biến một bài toán thành bài toán khác?

Gọi A là bài toán gốc và B là bài toán đã có lời giải. Một phép biến đổi đúng cần ba phần:

1. **Mã hóa đầu vào:** từ trường hợp x của A, tạo trường hợp f(x) cho B.
2. **Giải bài toán quen:** dùng thuật toán đã biết để tính y = solveB(f(x)).
3. **Giải mã kết quả:** chuyển y trở lại z = g(x, y), là kết quả hợp lệ cho A.

Sơ đồ:

~~~text
Dữ liệu của A
   |
   v
Biến đổi f (có điều kiện cần thỏa)
   |
   v
Dữ liệu / truy vấn của B
   |
   v
Thuật toán đã biết solveB
   |
   v
Đáp án của B
   |
   v
Khôi phục g hoặc diễn giải lại
   |
   v
Đáp án theo hợp đồng của A
~~~

Ví dụ, bài toán hỏi “có đoạn liên tiếp nào có tổng T không?” có thể đổi thành câu hỏi “trong những tổng tiền tố đã xuất hiện, có giá trị nào bằng tổng hiện tại trừ T không?”. Hai cách nói trông khác nhau, nhưng được nối bằng một đẳng thức chính xác.

**Phân biệt với xấp xỉ:** một phép biến đổi mà chỉ giữ gần đúng giá trị tối ưu chưa đủ để dùng như quy giảm chính xác. Nếu yêu cầu đáp án đúng tuyệt đối, phải chứng minh kết quả dựng lại cũng đúng tuyệt đối.

**Phân biệt với thay đổi đề bài:** nếu A yêu cầu đoạn *liên tiếp*, không thể bỏ điều kiện liên tiếp rồi giải một bài toán chọn tập con bất kỳ; đó là một bài toán khác, dù cùng có từ “tổng”.

## 2. Hợp đồng cần giữ: đúng chiều, đủ chiều và khôi phục

Trước khi tin một phép quy giảm, hãy viết rõ:

- **Đúng chiều (soundness):** mỗi lời giải B được chọn và giải mã phải tạo ra một đáp án hợp lệ cho A. Không đưa về A một ứng viên vi phạm ràng buộc ban đầu.
- **Đủ chiều (completeness):** mỗi lời giải hợp lệ cần xét của A phải được phản ánh trong B; phép chuyển không được bỏ sót đáp án tốt hơn.
- **Bảo toàn mục tiêu tối ưu:** khi A hỏi “dài nhất”, “ngắn nhất”, “ít nhất”, cần chứng minh cách chọn kết quả trong B cũng tối ưu cho A, không chỉ chứng minh sự tồn tại.
- **Khôi phục đầu ra:** A có thể cần chỉ số gốc, dãy thao tác, danh sách đỉnh hoặc một lịch thực tế, chứ không chỉ giá trị số.
- **Tính toán được với chi phí hợp lý:** chi phí dựng f, giải B và dựng g đều phải nằm trong phân tích.

Chẳng hạn, sắp xếp dữ liệu có thể giúp áp dụng kỹ thuật hai con trỏ nhưng sẽ làm thay đổi vị trí các phần tử. Nếu đề cần trả về **chỉ số ban đầu**, hãy giữ cặp (giá trị, chỉ số) hoặc có cách ánh xạ ngược hợp lệ. Nếu đề chỉ hỏi số lượng hoặc giá trị, có thể không cần phục hồi thứ tự đầu vào.

Một phép biến đổi tốt thường làm cho **bất biến của thuật toán quen trở thành bất biến của bài toán gốc**. Bằng chứng phải đi qua ánh xạ chứ không chỉ nói “thuật toán này thường chạy đúng”.

## 3. Nhận ra cấu trúc quen từ cách hỏi đề bài

| Dấu hiệu trong bài toán | Cách biểu diễn lại | Kỹ thuật quen cần cân nhắc | Điều kiện cần kiểm tra |
| --- | --- | --- | --- |
| Tổng một **đoạn liên tiếp** | Hiệu hai tổng tiền tố | Prefix sum + HashMap, hoặc truy vấn prefix | Biên đoạn, overflow, có số âm hay không |
| Nhiều truy vấn tổng đoạn | Tiền xử lý mảng tổng tiền tố | Trả truy vấn O(1) sau O(n) | Mảng có thay đổi giữa truy vấn không |
| Số hoạt động diễn ra cùng lúc | Điểm bắt đầu/kết thúc của các khoảng | Sweep line, sắp xếp sự kiện | Quy ước khoảng đóng/nửa mở và xử lý đồng thời |
| Ít phòng/tài nguyên tối thiểu cho các khoảng | Đỉnh số khoảng chồng nhau | Quét endpoint | Tài nguyên có thể tái sử dụng ngay khi kết thúc không |
| Đường đi ngắn nhất trên lưới không trọng số | Ô hợp lệ là đỉnh, bước đi là cạnh | BFS trên đồ thị ẩn | Mỗi bước cùng chi phí, quy tắc di chuyển |
| Khóa nguyên rất rộng nhưng ít giá trị phân biệt | Thứ hạng 0..k−1 của các khóa | Nén tọa độ, cấu trúc Fenwick / segment tree | Cần giữ quan hệ thứ tự và ánh xạ ngược |
| Bài toán chọn nhiều lựa chọn với ràng buộc phụ thuộc | Trạng thái + chuyển trạng thái | Dynamic programming / đồ thị trạng thái | Trạng thái có đủ thông tin, không bỏ điều kiện |
| Bài toán với thứ tự hoặc các khoảng trên trục | Sắp xếp rồi xử lý tuần tự | Two pointers, binary search, greedy | Sắp xếp có giữ được thông tin cần trả về |

Bảng là **danh sách gợi ý**, không phải phép chứng minh rằng kỹ thuật luôn áp dụng. Ví dụ BFS chỉ cho đường đi ngắn nhất theo số cạnh khi các bước có cùng trọng số; nếu cạnh có trọng số dương khác nhau, cần xét Dijkstra hoặc thuật toán phù hợp khác.

## 4. Ví dụ chính: tìm đoạn liên tiếp dài nhất có tổng bằng T

**Đề bài A:** cho mảng số nguyên a độ dài n (cho phép âm, 0 và trùng), cùng số T. Tìm **đoạn liên tiếp không rỗng dài nhất** có tổng bằng T.

Hợp đồng kết quả:

- Trả về cặp chỉ số **[start, end)**, gồm các vị trí start, start+1, ..., end−1.
- Nếu có nhiều đoạn có độ dài lớn nhất bằng nhau, chọn đoạn có **start nhỏ nhất**.
- Nếu không có đoạn phù hợp, trả về **[-1, -1]**.
- Mảng rỗng không có đoạn không rỗng, nên cũng trả [-1, -1].
- Mảng không được sắp xếp lại; các chỉ số phải thuộc mảng đầu vào ban đầu.

Vét cạn xét mọi start, mọi end > start và tính tổng của từng đoạn, có thể O(n²) nếu dùng tổng cộng dồn từ mỗi start; cách ngây thơ tính lại tổng cho mọi đoạn còn tốn hơn.

Ta muốn áp dụng một bài toán đã biết: **tra cứu sự tồn tại của một khóa trong HashMap**. Điều còn thiếu là ánh xạ chính xác từ “tổng của đoạn” sang “khóa cần tra”.

## 5. Biến đổi bằng tổng tiền tố và đẳng thức hai chiều

Đặt P[0] = 0 và P[r] = a[0] + a[1] + ... + a[r−1] với 1 ≤ r ≤ n.

Tổng đoạn [l, r), với 0 ≤ l < r ≤ n, bằng:

~~~text
sum(a[l .. r-1]) = P[r] - P[l].
~~~

Vì thế điều kiện tổng bằng T tương đương:

~~~text
P[r] - P[l] = T
<=> P[l] = P[r] - T.
~~~

Đây là một **tương đương hai chiều**. Mỗi đoạn có tổng T tạo ra một cặp tổng tiền tố thỏa hiệu T, và mỗi cặp chỉ số tiền tố l < r thỏa hiệu T tạo ra đúng một đoạn liên tiếp hợp lệ.

Khi duyệt r tăng dần, ta biết P[r]. Chỉ cần hỏi **HashMap đã thấy khóa P[r] − T ở vị trí l nào trước đó chưa?**. Như vậy ta đưa bài toán tính tổng đoạn về **bài toán tra cứu khóa chính xác**, có O(1) thời gian trung bình cho mỗi lần tra.

**Vì sao phải lưu cả chỉ số?** Nếu chỉ ghi một cờ “đã gặp prefix”, ta có thể biết có một đoạn phù hợp nhưng không khôi phục được [l, r). Hợp đồng A yêu cầu chỉ số nên phải có ánh xạ từ giá trị prefix về vị trí l.

## 6. Vì sao phải lưu chỉ số xuất hiện sớm nhất?

Tại đầu một lượt xét r, ánh xạ earliest chứa tổng tiền tố P[l] → **chỉ số l nhỏ nhất đã gặp**, với 0 ≤ l < r.

Nếu P[r] − T xuất hiện nhiều lần, chọn l **nhỏ nhất** tạo ra đoạn [l, r) có **độ dài r−l lớn nhất** trong tất cả các đoạn kết thúc tại r. Vì thế chỉ giữ vị trí sớm nhất cho từng tổng tiền tố là đủ để tìm đáp án dài nhất toàn cục.

Ba chi tiết triển khai:

1. Khởi tạo **earliest[0] = 0** trước khi đọc phần tử đầu tiên. Nếu bỏ P[0], ta sẽ bỏ sót mọi đoạn bắt đầu tại chỉ số 0.
2. Với mỗi r từ 1 tới n, tính prefix hiện tại, **tra cứu P[r]−T trước**, sau đó mới dùng **putIfAbsent(prefix, r)**. Việc này bảo đảm chỉ xét l < r, nên đoạn không rỗng.
3. Không ghi đè chỉ số đã lưu của cùng tổng tiền tố. Ghi đè bằng vị trí mới hơn có thể làm mất đoạn dài hơn.

Khi tìm được một ứng viên [l, r), cập nhật nếu nó dài hơn kết quả hiện tại; nếu độ dài bằng nhau, chỉ thay khi l nhỏ hơn. Tại cuối, kết quả dài nhất được tìm giữa tất cả r. Quy tắc hòa này tạo ra kết quả xác định.

**Cảnh báo hai con trỏ:** cửa sổ trượt theo tổng thường chỉ điều chỉnh được một chiều nếu các số không âm. Với số âm, mở rộng có thể làm tổng giảm và thu hẹp có thể làm tổng tăng, nên không được máy móc áp dụng cách “tổng lớn thì rút trái”. Công thức tổng tiền tố không cần giả thiết không âm.

## 7. Lần theo ví dụ có số âm và hai đáp án cùng độ dài

Với a = [3, −2, 5, −1, 2, −2] và T = 4, tổng tiền tố:

~~~text
P[0..6] = [0, 3, 1, 6, 5, 7, 5].
~~~

Ta tra khóa cần tìm P[r] − 4.

| r (biên cuối) | P[r] | P[r]−4 | Có prefix sớm hơn? | Kết quả / hành động |
| ---: | ---: | ---: | --- | --- |
| 1 | 3 | −1 | Không | Lưu P[1]=3 tại r=1 |
| 2 | 1 | −3 | Không | Lưu P[2]=1 tại r=2 |
| 3 | 6 | 2 | Không | Lưu P[3]=6 tại r=3 |
| 4 | 5 | 1 | Có, P[2]=1 | [2,4), tổng 5+(−1)=4, độ dài 2 |
| 5 | 7 | 3 | Có, P[1]=3 | [1,5), tổng −2+5−1+2=4, độ dài 4 |
| 6 | 5 | 1 | Có, P[2]=1 | [2,6), tổng 5−1+2−2=4, độ dài 4 |

Đoạn [1,5) và [2,6) cùng dài 4. Theo quy tắc chọn **start nhỏ nhất**, đáp án là **[1,5)**. Nếu chỉ lưu một chỉ số tùy ý cho P[l], hoặc dùng chiến lược chỉ dừng ở ứng viên đầu tiên, có thể đưa ra đoạn ngắn hoặc chọn sai quy tắc hòa.

**Trường hợp T = 0 và nhiều số 0:** với [0,0,0], prefix ở mọi bước đều là 0. Giữ earliest[0]=0 sẽ cho đoạn dài nhất [0,3), không phải ba đoạn độ dài 1.

## 8. Chứng minh phép biến đổi và thuật toán HashMap đúng

**Đúng chiều:** bất cứ ứng viên [l,r) nào thuật toán lấy từ lookup đều có 0 ≤ l < r ≤ n và P[l] = P[r]−T, nên tổng đoạn bằng T. Thuật toán không trả về đoạn có tổng sai.

**Đủ chiều:** xét một đoạn hợp lệ bất kỳ [l,r). Khi duyệt tới r, P[l] đã có trong earliest vì l < r. Có thể map ghi một chỉ số l0 ≤ l thay vì l nếu tổng tiền tố P[l] xuất hiện trước, nhưng [l0,r) vẫn có tổng T và không ngắn hơn [l,r). Vì vậy không bỏ sót cơ hội đạt độ dài tối ưu.

**Tối ưu và hòa:** ở mỗi r, thuật toán xét ứng viên dài nhất trong các đoạn kết thúc tại r. So sánh qua tất cả r đưa ra độ dài lớn nhất toàn cục; nếu bằng độ dài, điều kiện start nhỏ nhất giữ đúng quy tắc hòa.

**Kết thúc:** vòng for chạy đúng n lần, không có đệ quy; mọi thao tác tính toán và tra cứu trên một lượt là hữu hạn. Khi n = 0, không vào vòng và trả đúng [-1,-1].

**Bảo toàn dữ liệu:** thuật toán chỉ đọc mảng đầu vào; không sắp xếp hay thay đổi chỉ số gốc. Đây là điều kiện quan trọng của phép khôi phục.

**Độ phức tạp:** tính prefix trong một lượt; mỗi lần thao tác HashMap có thời gian O(1) **trung bình**, nên tổng thời gian trung bình O(n), bộ nhớ phụ O(n) cho tối đa n+1 giá trị prefix. Không gọi O(1) HashMap là cam kết tuyệt đối trong mọi tình huống va chạm hash.

## 9. Tràn số: phép biến đổi đại số đúng nhưng kiểu dữ liệu có thể sai

Tổng của các phần tử int có thể vượt miền biểu diễn int. Ví dụ Integer.MAX_VALUE + Integer.MAX_VALUE = 4.294.967.294, nhưng int không chứa được giá trị đó. Nếu prefix bị tràn và wrap, điều kiện hiệu hai prefix có thể không còn phản ánh phép cộng trên số nguyên toán học, dẫn đến đối chiếu sai.

Chương trình Java dùng **long** cho tổng tiền tố và target, cùng HashMap<Long,Integer>. Với một mảng Java int có chiều dài hợp lệ, tổng các phần tử nằm trong giới hạn long, nên cách cộng này đáp ứng miền dữ liệu của ví dụ. Những bài toán dùng long đầu vào với số phần tử rất lớn phải đánh giá lại tràn số và có thể cần BigInteger.

Đừng nhầm việc biến đổi được chứng minh trên số nguyên toán học với khả năng thực thi an toàn trong kiểu dữ liệu hữu hạn. **Chứng minh đúng cần bao gồm giả thiết về biểu diễn số.**

## 10. Ví dụ thứ hai: số phòng họp ít nhất chuyển thành số khoảng chồng nhau lớn nhất

**Đề bài A:** cho n cuộc họp, cuộc họp i chiếm khoảng thời gian **[start_i, end_i)** với start_i < end_i. Cần bao nhiêu phòng ít nhất để không có hai cuộc họp cùng sử dụng một phòng ở thời điểm chồng nhau?

Quy ước nửa mở rất quan trọng: cuộc họp [0,2) kết thúc đúng lúc 2 và cuộc họp [2,4) bắt đầu lúc 2 **có thể dùng cùng một phòng**. Mảng cuộc họp rỗng cần 0 phòng.

**Biến đổi:** yêu cầu số phòng tối thiểu bằng **số cuộc họp đồng thời lớn nhất**. Ta không cần thử mọi cách gán phòng. Thay vào đó, lấy hai dãy thời điểm bắt đầu và kết thúc, sắp xếp chúng, rồi quét các mốc bắt đầu theo thứ tự.

- Mỗi cuộc họp đang diễn ra cần một phòng, nên số phòng tối thiểu **không thể nhỏ hơn** số cuộc họp chồng nhau cực đại.
- Ngược lại, nếu đang có q cuộc họp thì cần q phòng. Khi cuộc họp kết thúc, phòng của nó sẵn sàng tái sử dụng. Xử lý lịch theo thứ tự bắt đầu cho phép cấp phòng rảnh trước khi mở phòng mới. Vì thế có thể tổ chức lịch với đúng số phòng bằng đỉnh chồng nhau.

Đó là lập luận **hai chiều**: một phía là cận dưới bắt buộc, phía kia là chứng minh có cách đạt được cận dưới.

## 11. Quy tắc sắp xếp endpoint và bất biến sweep line

Tạo hai mảng starts[], ends[] có cùng độ dài n rồi **sắp xếp riêng từng mảng**. Duyệt mỗi thời điểm bắt đầu theo thứ tự tăng:

1. Giải phóng mọi cuộc họp có end ≤ start đang xét.
2. Tăng số cuộc họp đang hoạt động thêm một cho cuộc họp vừa bắt đầu.
3. Ghi lại số hoạt động lớn nhất.

**Bất biến:** ngay trước khi thêm cuộc họp bắt đầu tại thời điểm start, sau khi xử lý mọi end ≤ start, biến active bằng số cuộc họp đã bắt đầu trước đó nhưng chưa kết thúc tại start. Sau khi tăng, active là số cuộc họp đang hoạt động gồm cả cuộc họp mới. Giá trị lớn nhất qua mọi lần thêm bằng đỉnh chồng nhau.

**Vì sao khi end = start phải giải phóng trước?** Với [s,e), thời điểm e không còn thuộc khoảng. Nếu xử lý sự kiện bắt đầu trước sự kiện kết thúc cùng thời điểm, chương trình sẽ đếm thừa một cuộc họp và có thể yêu cầu thêm phòng không cần thiết.

**Vì sao có thể sắp starts và ends riêng, làm mất từng cặp ban đầu?** Để tính số cuộc họp đang hoạt động, ta chỉ cần số lượt bắt đầu và kết thúc trước mỗi mốc, không cần biết “kết thúc này thuộc cuộc họp nào”. Điều này **không có nghĩa** có thể dùng kết quả đó để dựng trực tiếp bản phân phòng cụ thể; nếu bài toán yêu cầu phòng của từng cuộc họp, ta phải giữ thông tin nhận dạng và dùng cấu trúc phân phòng thích hợp.

**Giả thiết:** mọi khoảng đều có start < end. Nếu cho phép khoảng rỗng [t,t), cần xác định cách xử lý vì cuộc họp đó không chiếm thời lượng; chương trình ví dụ từ chối khoảng có start ≥ end thay vì âm thầm coi nó là một cuộc họp thực.

## 12. Theo dõi ví dụ lịch họp

Các cuộc họp:

~~~text
A: [0,3)
B: [2,4)
C: [2,5)
D: [4,6)
~~~

Sau khi chuyển thành hai dãy có thứ tự:

~~~text
starts = [0, 2, 2, 4]
ends   = [3, 4, 5, 6]
~~~

| Lần mở họp | start | Kết thúc được giải phóng trước | active sau khi mở | max |
| --- | ---: | --- | ---: | ---: |
| A | 0 | Không | 1 | 1 |
| B | 2 | Không | 2 | 2 |
| C | 2 | Không | 3 | 3 |
| D | 4 | 3 và 4 | 2 | 3 |

Tại thời điểm 2, ba cuộc họp A, B, C cùng hoạt động nên bắt buộc có ít nhất 3 phòng. Từ thời điểm 4, A và B đã kết thúc; D có thể dùng lại một trong các phòng rảnh, và không thời điểm nào vượt quá 3. Do đó số phòng ít nhất là **3**.

Chỉ thay một chi tiết quy ước, chẳng hạn coi end = start vẫn chồng nhau, có thể đổi đáp án. Vì vậy phải viết rõ quy ước biên trước khi chọn thuật toán sweep line.

## 13. Hai ví dụ: tiền xử lý, bảo toàn và độ phức tạp

| Thuộc tính | Đoạn tổng T dài nhất | Số phòng ít nhất |
| --- | --- | --- |
| Bài toán gốc | Tối ưu độ dài đoạn liên tiếp có tổng T | Tối thiểu tài nguyên cho các khoảng |
| Biến đổi | Tổng đoạn → hiệu hai tổng tiền tố | Phân phòng → đếm số khoảng đồng thời |
| Công cụ đã biết | HashMap tra cứu khóa | Sắp xếp và quét hai dãy endpoint |
| Dữ liệu bổ sung | Giá trị prefix → chỉ số sớm nhất | Hai mảng starts và ends |
| Tiền điều kiện trọng yếu | Đoạn không rỗng, tổng dùng long | start < end, khoảng nửa mở |
| Cách khôi phục | Trả [start,end) trên mảng gốc | Trả giá trị đỉnh số cuộc họp |
| Thời gian | O(n) trung bình | Thường O(n log n) do sắp xếp |
| Bộ nhớ phụ | O(n) | O(n) cho hai mảng endpoint |
| Mất thông tin? | Không mất vị trí cần khôi phục | Mất cặp ID nhưng không cần cho đầu ra số phòng |

Cần tính **cả phép biến đổi**: tạo prefix có thể làm trực tiếp trong một lượt; tạo hai mảng endpoint mất O(n), sắp xếp thường O(n log n), rồi quét O(n). Nếu chỉ ghi chi phí quét O(n) và kết luận toàn bộ bài phòng họp là O(n), đó là bỏ sót bước tiền xử lý.

Với sắp xếp số nguyên Java, trường hợp xấu cụ thể còn tùy phiên bản/hiện thực Arrays.sort. Kết luận O(n log n) là mức phân tích thường dùng cho cách tiếp cận sắp xếp endpoint, và có thể được bảo đảm bằng thuật toán sắp xếp so sánh thích hợp nếu bài toán yêu cầu ràng buộc chặt.

## 14. Java 17+: chương trình độc lập chứng minh hai phép biến đổi

Tệp **KnownProblemReductions.java** sau triển khai hai phương thức công khai:

- longestTargetSubarray(a, target) trả [start,end) với độ dài lớn nhất, ưu tiên start nhỏ nhất; không thay đổi a, cho phép số âm, số 0 và tổng vượt int.
- minRooms(intervals) trả số phòng tối thiểu đối với các khoảng nửa mở không rỗng; không thay đổi intervals, nhưng sẽ tạo và sắp xếp hai mảng phụ.
- Hai bộ oracle vét cạn chỉ sử dụng trong kiểm thử: bruteLongest duyệt mọi đoạn; bruteRooms đếm số khoảng hoạt động theo từng thời điểm nguyên trên bộ test có endpoint từ 0 tới 4.

Các phương thức công khai ném IllegalArgumentException nếu gặp đầu vào null hoặc khoảng không hợp lệ, thay vì âm thầm tạo đáp án cho đầu vào ngoài hợp đồng.

~~~java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

public final class KnownProblemReductions {
    private KnownProblemReductions() {
    }

    public static int[] longestTargetSubarray(int[] a, long target) {
        if (a == null) {
            throw new IllegalArgumentException("array must not be null");
        }

        Map<Long, Integer> earliest = new HashMap<>();
        earliest.put(0L, 0);
        long prefix = 0L;
        int bestStart = -1;
        int bestEnd = -1;
        int bestLength = 0;

        for (int end = 1; end <= a.length; end++) {
            prefix += a[end - 1];
            Integer start = earliest.get(prefix - target);
            if (start != null) {
                int length = end - start;
                if (length > bestLength
                        || (length == bestLength && start < bestStart)) {
                    bestStart = start;
                    bestEnd = end;
                    bestLength = length;
                }
            }
            earliest.putIfAbsent(prefix, end);
        }
        return new int[] {bestStart, bestEnd};
    }

    public static int minRooms(int[][] intervals) {
        if (intervals == null) {
            throw new IllegalArgumentException("intervals must not be null");
        }

        int n = intervals.length;
        int[] starts = new int[n];
        int[] ends = new int[n];

        for (int i = 0; i < n; i++) {
            if (intervals[i] == null || intervals[i].length != 2
                    || intervals[i][0] >= intervals[i][1]) {
                throw new IllegalArgumentException("require start < end");
            }
            starts[i] = intervals[i][0];
            ends[i] = intervals[i][1];
        }

        Arrays.sort(starts);
        Arrays.sort(ends);
        int finished = 0;
        int active = 0;
        int maxActive = 0;

        for (int start : starts) {
            while (finished < n && ends[finished] <= start) {
                active--;
                finished++;
            }
            active++;
            if (active > maxActive) {
                maxActive = active;
            }
        }
        return maxActive;
    }

    private static int[] bruteLongest(int[] a, long target) {
        int bestStart = -1;
        int bestEnd = -1;
        int bestLength = 0;
        for (int start = 0; start < a.length; start++) {
            long sum = 0;
            for (int end = start + 1; end <= a.length; end++) {
                sum += a[end - 1];
                int length = end - start;
                if (sum == target && (length > bestLength
                        || (length == bestLength && start < bestStart))) {
                    bestStart = start;
                    bestEnd = end;
                    bestLength = length;
                }
            }
        }
        return new int[] {bestStart, bestEnd};
    }

    private static int bruteRooms(int[][] intervals) {
        int best = 0;
        for (int time = 0; time < 4; time++) {
            int active = 0;
            for (int[] interval : intervals) {
                if (interval[0] <= time && time < interval[1]) {
                    active++;
                }
            }
            best = Math.max(best, active);
        }
        return best;
    }

    private static void verify() {
        int[] alphabet = {-2, -1, 0, 1, 2};
        int checkedSubarrays = 0;
        for (int n = 0; n <= 5; n++) {
            int combinations = 1;
            for (int i = 0; i < n; i++) {
                combinations *= alphabet.length;
            }
            for (int code = 0; code < combinations; code++) {
                int[] a = new int[n];
                int remaining = code;
                for (int i = 0; i < n; i++) {
                    a[i] = alphabet[remaining % alphabet.length];
                    remaining /= alphabet.length;
                }
                for (int target = -4; target <= 4; target++) {
                    int[] expected = bruteLongest(a, target);
                    int[] actual = longestTargetSubarray(a, target);
                    if (!Arrays.equals(expected, actual)) {
                        throw new AssertionError("Subarray mismatch on "
                                + Arrays.toString(a) + ", target=" + target);
                    }
                    checkedSubarrays++;
                }
            }
        }

        int[][] choices = {
            {0, 1}, {0, 2}, {1, 2}, {1, 3},
            {2, 3}, {2, 4}, {3, 4}
        };
        int checkedIntervals = 0;
        for (int n = 0; n <= 4; n++) {
            int combinations = 1;
            for (int i = 0; i < n; i++) {
                combinations *= choices.length;
            }
            for (int code = 0; code < combinations; code++) {
                int[][] intervals = new int[n][2];
                int remaining = code;
                for (int i = 0; i < n; i++) {
                    int[] choice = choices[remaining % choices.length];
                    intervals[i][0] = choice[0];
                    intervals[i][1] = choice[1];
                    remaining /= choices.length;
                }
                if (minRooms(intervals) != bruteRooms(intervals)) {
                    throw new AssertionError("Interval mismatch");
                }
                checkedIntervals++;
            }
        }
        System.out.println("Verified " + checkedSubarrays
                + " subarray cases: PASS");
        System.out.println("Verified " + checkedIntervals
                + " interval cases: PASS");
    }

    public static void main(String[] args) {
        int[] a = {3, -2, 5, -1, 2, -2};
        System.out.println("subarray target 4 = "
                + Arrays.toString(longestTargetSubarray(a, 4)));
        System.out.println("subarray target 0 = "
                + Arrays.toString(longestTargetSubarray(
                        new int[] {0, 0, 0}, 0)));
        System.out.println("no match = "
                + Arrays.toString(longestTargetSubarray(
                        new int[] {1, 2, 3}, 20)));
        System.out.println("large sum = "
                + Arrays.toString(longestTargetSubarray(
                        new int[] {Integer.MAX_VALUE, Integer.MAX_VALUE,
                                   Integer.MIN_VALUE, -1},
                        2L * Integer.MAX_VALUE)));
        System.out.println("rooms = "
                + minRooms(new int[][] {
                    {0, 3}, {2, 4}, {2, 5}, {4, 6}
                }));
        System.out.println("touching rooms = "
                + minRooms(new int[][] {{0, 2}, {2, 4}}));
        System.out.println("empty rooms = " + minRooms(new int[0][2]));
        verify();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac KnownProblemReductions.java
java KnownProblemReductions
~~~

Đầu ra chính xác:

~~~text
subarray target 4 = [1, 5]
subarray target 0 = [0, 3]
no match = [-1, -1]
large sum = [0, 2]
rooms = 3
touching rooms = 1
empty rooms = 0
Verified 35154 subarray cases: PASS
Verified 2801 interval cases: PASS
~~~

Dòng **Verified 35154 subarray cases: PASS** là kết quả duyệt mọi mảng có độ dài từ 0 tới 5 trên tập {-2,−1,0,1,2}, tương ứng:

~~~text
Số mảng = 5^0 + 5^1 + 5^2 + 5^3 + 5^4 + 5^5 = 3906.
Mỗi mảng thử target từ -4 tới 4: 9 giá trị.
Số ca = 3906 × 9 = 35154.
~~~

Dòng **Verified 2801 interval cases: PASS** là kết quả duyệt mọi danh sách có độ dài từ 0 tới 4 chọn từ 7 khoảng hợp lệ: 1+7+49+343+2401 = 2801 danh sách. Với các khoảng thử chỉ có mốc nguyên 0..4, đếm active tại các thời điểm 0,1,2,3 đủ để xác định đỉnh: số khoảng đang hoạt động chỉ thay đổi tại các endpoint nguyên và khoảng rỗng bị loại.

Cách kiểm thử này so sánh **phương pháp quy giảm** với **oracle trực tiếp** độc lập, chứ không lấy cùng một hiện thực làm tiêu chuẩn cho chính nó. Dù tất cả ca nhỏ đều PASS, chứng minh soundness/completeness vẫn cần để khẳng định đúng cho đầu vào tùy ý.

## 15. Lỗi thường gặp khi đưa về bài toán quen

1. **Giải sai biến thể.** Dùng bài toán “có tồn tại đoạn tổng T” để trả cho yêu cầu “đoạn dài nhất” mà không lưu vị trí sớm nhất của prefix.
2. **Làm mất ràng buộc gốc.** Đổi đoạn *liên tiếp* thành chọn một tập phần tử bất kỳ hoặc làm mất ID khi đề yêu cầu trả lại ID.
3. **Chỉ chứng minh một chiều.** “Nếu B có đáp án thì A có đáp án” chưa đủ nếu phép biến đổi bỏ sót các đáp án tối ưu của A.
4. **Quên khôi phục lời giải.** Trả số lượng mà đề đòi chỉ số, đường đi, lịch phân phòng hoặc chuỗi thao tác.
5. **Bỏ qua tính toán tràn số.** Dùng int cho prefix và phép trừ trong khi tổng có thể vượt int.
6. **Quên prefix đầu tiên.** Không có P[0]=0 làm mất các đoạn bắt đầu tại chỉ số 0.
7. **Ghi đè vị trí sớm nhất.** Dùng map.put(prefix,r) thay vì putIfAbsent, khiến các ứng viên dài hơn biến mất.
8. **Tra cứu sau khi chèn prefix hiện tại.** Với T=0 có thể tạo “đoạn rỗng” [r,r) nếu không yêu cầu l < r.
9. **Áp dụng sliding window bất kể số âm.** Định hướng tăng/giảm tổng không còn đơn điệu khi chứa số âm.
10. **Xử lý tie endpoint sai.** Khi khoảng là [start,end), end bằng start phải giải phóng trước khi mở cuộc họp mới.
11. **Bỏ qua chi phí biến đổi.** Phân tích quét endpoint O(n) nhưng quên sắp xếp O(n log n).
12. **Chuyển sai loại đồ thị.** Mô hình bài toán ngắn nhất có trọng số khác nhau nhưng vẫn dùng BFS như đồ thị không trọng số.
13. **Sai quy ước chỉ số.** Một nơi dùng [l,r), nơi khác dùng [l,r] sẽ gây lệch 1 trong tổng và độ dài.
14. **Bỏ qua input đặc biệt.** Mảng rỗng, không có đáp án, target=0, khoảng chạm biên hoặc dữ liệu có giá trị cực đại.

Phép quy giảm nên làm vấn đề **đơn giản hơn mà không làm yếu đặc tả**. Nếu phải bổ sung quá nhiều giả thiết không có trong đề bài, hãy xem lại việc chọn B.

## 16. Quy trình chọn phép biến đổi trong bài thi hoặc dự án

Dùng một checklist thực tế:

1. **Ghi rõ yêu cầu.** Đầu vào và đầu ra; có cần trả lại vị trí gốc, thứ tự, phương án cụ thể hay chỉ một giá trị?
2. **Tìm biểu thức/quan hệ cốt lõi.** Tổng, số khoảng chồng nhau, đường đi, thứ tự giá trị, điều kiện tồn tại hay một quan hệ đơn điệu?
3. **Liệt kê công cụ quen.** Prefix sum, HashMap, sorting/sweep line, binary search, BFS, Dijkstra, DP, union-find, đồ thị trạng thái, nén tọa độ.
4. **Đề xuất ánh xạ f.** Nêu chính xác dữ liệu nào tạo ra, kể cả cách giữ hoặc bỏ thông tin gốc.
5. **Chứng minh hai chiều.** Mỗi đáp án B giải mã hợp lệ cho A; mọi đáp án A liên quan đến tối ưu có đại diện tương ứng trong B.
6. **Kiểm tra mục tiêu tối ưu.** Độ dài, số lượng, tổng chi phí hay thứ tự hòa có được giữ sau biến đổi không?
7. **Tính chi phí thật.** Dựng dữ liệu + sắp xếp/tiền xử lý + giải B + khôi phục; tính bộ nhớ tạm và khả năng tràn số.
8. **Viết oracle nhỏ.** Duyệt hết trên n nhỏ, rồi so sánh với thuật toán mới trên nhiều dữ liệu tự sinh, kể cả ca biên.
9. **Kiểm tra giả thiết ngầm.** Số âm, phần tử trùng, khoảng chạm nhau, trọng số, vòng lặp, null/empty, chỉ số ban đầu và tính ổn định.

Nếu không chứng minh được hai chiều, thử xác định một **phản ví dụ nhỏ** thay vì tiếp tục tối ưu theo trực giác. Phản ví dụ thường chỉ ra một tiền điều kiện đã bị bỏ quên.

## 17. Bài tập tự luyện và mở rộng

**Bài 1 — Đoạn tổng bằng T ngắn nhất:** biến bài toán longestTargetSubarray thành tìm **đoạn không rỗng ngắn nhất** có tổng T, ưu tiên start nhỏ nhất khi hòa. Hãy phân tích vì sao giữ **prefix xuất hiện sớm nhất** không còn phù hợp với mục tiêu ngắn nhất và cần bảo đảm không sử dụng chỉ số r hiện tại trước khi tra.

**Bài 2 — Có đoạn tổng bằng 0:** đầu vào có cả số âm và dương. Biến “đã có prefix lặp lại hay chưa” thành thuật toán kiểm tra tồn tại đoạn không rỗng có tổng bằng 0. Chứng minh P[l]=P[r] với l<r tương đương có đoạn [l,r) tổng 0.

**Bài 3 — Dựng lịch phòng thật:** ngoài số phòng tối thiểu, hãy gán roomId cho từng cuộc họp. Nêu vì sao hai mảng starts/ends đã sắp xếp riêng không còn đủ thông tin ID, rồi thiết kế thuật toán có giữ từng cuộc họp và dùng min-heap theo thời điểm kết thúc để tái sử dụng phòng.

**Bài 4 — Các đoạn nửa mở:** thay đổi đặc tả để một cuộc họp kết thúc tại t và một cuộc họp bắt đầu tại t **không** được dùng chung phòng. Viết lại quy tắc đồng thời và cách xử lý sự kiện cùng thời điểm. Cho một ví dụ có đáp án khác.

**Bài 5 — Chuyển về đồ thị:** cho lưới ký tự, mỗi ô trống là đỉnh, bốn hướng di chuyển là cạnh có cùng giá 1. Định nghĩa phép mã hóa tọa độ thành đỉnh, quy tắc sinh hàng xóm và cách phục hồi đường đi từ mảng parent của BFS. Giải thích vì sao nếu một số bước có chi phí 2 thì BFS thường không còn đủ để tối ưu tổng chi phí.

**Tổng kết:** giải bài toán bằng quy giảm là năng lực **nhìn ra bài toán đã biết đằng sau biểu diễn mới**. Một phép biến đổi đáng tin có ánh xạ rõ ràng, chứng minh hai chiều, bảo toàn mục tiêu tối ưu, khôi phục được đúng đầu ra và tính đủ chi phí tiền xử lý. Kết hợp các điều đó với kiểm thử tham chiếu sẽ giúp biến một đề tưởng xa lạ thành một lời giải vừa hiệu quả vừa có căn cứ.

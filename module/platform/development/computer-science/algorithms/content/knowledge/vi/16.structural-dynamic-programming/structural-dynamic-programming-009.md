# Quy hoạch động theo chữ số và ràng buộc tiền tố

## 1. Digit DP giải quyết loại bài toán nào?

**Quy hoạch động theo chữ số (digit DP)** là kỹ thuật đếm, tính tổng hoặc tối ưu trên các số nguyên có chữ số thỏa điều kiện, đặc biệt khi miền tìm kiếm rất lớn nhưng số chữ số tương đối nhỏ. Thay vì duyệt từng số từ 0 đến N, ta dựng số **từng chữ số từ trái sang phải**, giữ thông tin đủ để quyết định những chữ số còn lại.

Những câu hỏi tiêu biểu:

- Có bao nhiêu số x trong khoảng [0,N] có **tổng chữ số chia hết cho 3**?
- Có bao nhiêu số trong [L,R] **không chứa chữ số 7**?
- Có bao nhiêu số có **không có hai chữ số kề nhau bằng nhau**?
- Có bao nhiêu số **không vượt N**, có đúng k chữ số khác 0?
- Có bao nhiêu số trong một khoảng có một **tiền tố bắt buộc** hoặc không chứa mẫu chữ số cấm?
- Tổng các giá trị x thỏa điều kiện bằng bao nhiêu? Hoặc số lớn nhất thỏa điều kiện là gì?

Đặc trưng của digit DP không nằm ở độ lớn của N mà ở việc **các ràng buộc của một tiền tố đã chọn có thể được mô tả bằng một số trạng thái nhỏ**. Với N có k chữ số thập phân, ta chỉ cần xử lý khoảng k vị trí; mỗi vị trí thử tối đa 10 chữ số, không cần liệt kê N+1 số.

Ví dụ minh họa xuyên suốt bài: đếm các số nguyên không âm x≤N sao cho:

1. Biểu diễn thập phân thông thường của x **không chứa chữ số 7**.
2. **Tổng các chữ số chia hết cho 3**.
3. **Không có hai chữ số kề nhau bằng nhau**.

Ta **tính số 0 là một nghiệm hợp lệ**: biểu diễn chuẩn của 0 là "0", không có chữ số 7, tổng chữ số bằng 0 và không có cặp chữ số kề nhau để vi phạm. Kết quả cho N=20 là 7: các số **0, 3, 6, 9, 12, 15, 18**.

Mô hình này thể hiện đồng thời cả ba loại trạng thái quan trọng: ràng buộc cận trên bằng tiền tố, các chữ số 0 đệm ở đầu và một ràng buộc phụ thuộc vào lịch sử chữ số đã chọn. Từ đó có thể mở rộng sang nhiều bài digit DP khác.

## 2. Tại sao duyệt thẳng không phù hợp khi N lớn?

Với cách vét cạn, ta xét từng x từ 0 đến N, tách các chữ số rồi kiểm tra điều kiện. Nếu một số có k chữ số, chi phí kiểm tra thường O(k), nên tổng thời gian có thể đến O((N+1)×k).

Khi N≈10^18, việc kiểm tra từng số là không khả thi. Nhưng N như vậy chỉ có **19 chữ số thập phân**. Digit DP tận dụng sự khác biệt ấy:

- Trạng thái chỉ chứa vị trí chữ số hiện tại và vài thông tin tóm tắt.
- Các tiền tố khác nhau mà có cùng thông tin tóm tắt có thể **dùng chung kết quả** cho phần hậu tố chưa chọn.
- Mọi chữ số tiếp theo được xét theo quy tắc **không vượt cận N**.

Với ví dụ của bài, trạng thái cần lưu vị trí, cờ sát cận trên, cờ đã bắt đầu số, tổng chữ số modulo 3 và chữ số thật cuối cùng. Số giá trị của những thông tin này rất nhỏ so với N.

**Điều kiện để áp dụng tốt:** sau khi đọc một tiền tố, mọi ảnh hưởng của nó đến lựa chọn tương lai phải được nén vào một bộ trạng thái hữu hạn, hoặc ít nhất có số trạng thái đủ nhỏ để chạy được. Nếu tương lai phụ thuộc vào toàn bộ tiền tố dài không nén được, digit DP tiêu chuẩn có thể không còn hiệu quả.

### Phân biệt với bài kiểm tra một số

Nếu chỉ kiểm tra **một** số x có đáp ứng điều kiện không, đọc chữ số của x một lần là đủ, O(k). Digit DP đặc biệt có giá trị khi phải **đếm/tổng hợp trên toàn miền rất lớn** hoặc trả lời nhiều cận khác nhau.

## 3. Tư duy dựng chữ số theo tiền tố và cận trên

Viết N dưới dạng chuỗi chữ số thập phân B=b[0]b[1]...b[k-1] không có số 0 vô nghĩa ở đầu, trừ chính số 0. Ta tạo một chuỗi k vị trí d[0]...d[k-1] từ trái sang phải, cho phép **đệm số 0 ở đầu** để mọi số trong [0,N] có cùng độ dài k.

Ví dụ với N=250:

~~~text
N                = 2 5 0
so 9  duoc dem  = 0 0 9
so 42 duoc dem  = 0 4 2
so 231 duoc dem = 2 3 1
so 250 duoc dem = 2 5 0
~~~

Cặp tiền tố được so sánh với N như khi so hai số có cùng độ dài:

- Nếu tiền tố đã chọn **bằng** tiền tố tương ứng của N, chữ số kế tiếp không được vượt b[pos].
- Nếu tiền tố đã chọn **nhỏ hơn** tiền tố của N, các vị trí còn lại được chọn tự do từ 0 đến 9.
- Không bao giờ cho phép tiền tố đã chọn **lớn hơn** tiền tố N; ta chặn từ lúc chọn chữ số.

Ta dùng cờ Boolean **tight**, tiếng Việt thường gọi là **còn sát cận**:

~~~text
tight = true:
    tat ca chu so da chon khop prefix cua N
    chu so ke tiep chi co the tu 0 den b[pos]

tight = false:
    tien to da nho hon tien to cua N
    chu so ke tiep co the tu 0 den 9
~~~

Khi tight=true và chọn chữ số d:

~~~text
maxDigit = b[pos]
nextTight = (d == b[pos])
~~~

Nếu tight=false thì maxDigit=9 và nextTight vẫn là false, **ngay cả khi d vô tình bằng chữ số b[pos] ở vị trí này**. Một tiền tố đã nhỏ hơn N không thể trở lại bằng N nhờ chữ số phía sau.

Công thức tổng quát chính xác là:

~~~text
limit     = tight ? boundDigit : 9
nextTight = tight AND (digit == boundDigit)
~~~

**Ví dụ N=250:**

- Chọn chữ số đầu 1: 1<2, tight=false; hai chữ số sau mỗi chữ số đều có thể 0..9.
- Chọn chữ số đầu 2 rồi chữ số tiếp 3: tiền tố 23 nhỏ hơn 25, tight=false; chữ số cuối có thể 0..9.
- Chọn 2 rồi 5: tiền tố vẫn bằng 25, tight=true; chữ số cuối chỉ được là 0.
- Không được chọn 2,5,1 vì 251 vượt N.

Chính cờ tight mã hóa **ràng buộc tiền tố do cận N**, một yếu tố trung tâm của digit DP.

## 4. Leading zeros và trạng thái started: số 0 đệm không phải chữ số thật

Khi đệm các số ngắn thành k chữ số, số 9 được biểu diễn trong quá trình duyệt N=250 thành "009". Hai số 0 đầu là **ký tự đệm**, không phải hai chữ số thuộc biểu diễn thông thường của số 9.

Nếu đếm số lần xuất hiện chữ số 0, cấm hai chữ số liền nhau bằng nhau hoặc kiểm tra tiền tố thực của số, việc xem các số 0 đệm như chữ số thật sẽ gây sai nghiêm trọng.

Dùng cờ **started**:

- started=false: chưa chọn chữ số thực sự khác 0 nào; mọi chữ số 0 đã chọn đều là **leading zeros**.
- started=true: đã chọn được chữ số khác 0 đầu tiên; mọi chữ số về sau, kể cả số 0, là chữ số **thật** của số đang dựng.

Khi thử chữ số d tại vị trí tiếp theo:

~~~text
if started == false AND d == 0:
    nextStarted = false
    // Van dang o phan dem so 0 dau.
else:
    nextStarted = true
    // d la chu so that, kiem tra cac rang buoc.
~~~

Các hệ quả:

- Với N=250, biểu diễn "009" được hiểu là số 9, không có cặp hai số 0 thật kề nhau.
- "010" được hiểu là 10: số 0 đầu là đệm, số 0 cuối **là chữ số thật**.
- "100" có hai chữ số 0 thật kề nhau, nên bị loại nếu cấm hai chữ số kề nhau bằng nhau.
- "000" đại diện cho **một** số nguyên 0, không phải ba chữ số 0 thực theo các điều kiện về vị trí.

### Xử lý số 0 như thế nào?

Nếu không có chữ số nào khác 0 được chọn, ended state có started=false và đại diện cho x=0. Trong bài minh họa, x=0 hợp lệ nên trạng thái này được **tính là một nghiệm**.

Trong bài toán yêu cầu số **dương**, phải loại started=false khi cộng đáp án. Trong bài toán “số có chính xác một chữ số 0”, cần đặc tả số 0 có một chữ số 0 hay không; thường biểu diễn chuẩn "0" có một chữ số 0, nên phải xử lý riêng x=0.

**Không tự động đếm trạng thái chưa bắt đầu trong mọi bài.** Quy tắc chấp nhận x=0 phải xuất phát từ đề bài, nhất quán với việc giải thích leading zeros.

## 5. Thiết kế trạng thái cho điều kiện cụ thể

Với ví dụ của bài, một trạng thái sau khi chọn xong một tiền tố gồm:

~~~text
pos      : vi tri ke tiep can dien, tu 0 den k
tight    : 1 neu tien to dang bang prefix N, 0 neu da nho hon
started  : 1 neu da bat dau so, 0 neu chi chon so 0 dem
rem      : tong cac chu so that modulo 3, thuoc {0,1,2}
prev     : chu so that gan nhat, thuoc {0,...,9},
           hoac sentinel 10 neu chua co chu so that
~~~

Đây là **trạng thái đủ (sufficient state)** vì tương lai chỉ cần biết:

- pos để biết đã chọn tới đâu và còn bao nhiêu chữ số.
- tight để áp giới hạn b[pos] của N.
- started để tránh xét số 0 đệm như chữ số thật.
- rem để biết cần tổng chữ số cuối cùng chia hết cho 3 hay không.
- prev để kiểm tra chữ số mới có bằng chữ số thật liền trước không.

Ta **không cần nhớ toàn bộ tiền tố** vì không điều kiện nào ở đây phụ thuộc vào chi tiết tiền tố ngoài năm biến trên.

### Chuyển trạng thái

Giả sử đang ở (pos,tight,started,rem,prev). Ta thử d từ 0 đến limit, với limit=tight?b[pos]:9.

**Trường hợp A: d là số 0 đệm**

Nếu started=false và d=0:

~~~text
nextStarted = false
nextRem     = 0
nextPrev    = 10  // Chua co chu so that.
nextTight   = tight AND (d == b[pos])
~~~

Không kiểm tra cặp chữ số kề nhau; không có chữ số thực nào để so. Tổng thực vẫn bằng 0.

**Trường hợp B: d là chữ số thật**

Nếu started=true hoặc d≠0, áp dụng các điều kiện:

1. Nếu d=7: bỏ nhánh, vì điều kiện **cấm chữ số 7**.
2. Nếu started=true và d=prev: bỏ nhánh, vì có hai chữ số thật liên tiếp bằng nhau.
3. Ngược lại:

~~~text
nextStarted = true
nextRem     = (rem + d) % 3
nextPrev    = d
nextTight   = tight AND (d == b[pos])
~~~

Nếu chữ số d là chữ số thực đầu tiên, prev đang là sentinel 10 nên không có cặp kề nhau để kiểm tra. Chữ số d=0 **vẫn có thể là thật** sau khi started=true và phải được kiểm tra giống các chữ số khác.

### Điều kiện chấp nhận khi hết chữ số

Khi pos=k, chỉ những trạng thái có rem=0 được nhận, vì tổng chữ số phải chia hết cho 3. Các nhánh chứa chữ số 7 hoặc hai chữ số kề nhau bằng nhau đã bị loại ngay trong chuyển trạng thái.

Ta cộng:

- Tất cả trạng thái started=true, rem=0, prev là chữ số thật từ 0..9, bất kể tight.
- Trạng thái started=false, rem=0, prev=10, đại diện cho **x=0**, cũng bất kể tight.

Không cần kiểm tra chữ số cuối thêm lần nữa: mọi vi phạm đã bị loại. Cũng không cần chọn ra **một** tiền tố tốt nhất; đây là bài **đếm**, nên mọi tiền tố hợp lệ đều đóng góp số cách.

## 6. Top-down có nhớ: hàm dfs và điểm dừng

Một cách viết tự nhiên là hàm đệ quy:

~~~text
dfs(pos, tight, started, rem, prev):
    if pos == numberOfDigits:
        return 1 neu rem == 0 va so 0 duoc phep, nguoc lai 0

    answer = 0
    limit = boundDigit[pos] neu tight else 9

    for digit from 0 to limit:
        if digit vi pham chu so cam / hai chu so lien tiep:
            continue
        nextState = update(tight, started, rem, prev, digit)
        answer += dfs(pos+1, nextState)

    return answer
~~~

Hàm đệ quy này sẽ gặp lại cùng trạng thái nhiều lần qua những tiền tố khác nhau. Ví dụ nhiều tiền tố đã nhỏ hơn N (tight=false) và cùng rem, prev, started sẽ có cùng số cách hoàn thành các chữ số còn lại. **Memoization** lưu kết quả cho những trạng thái ấy để mỗi trạng thái logic chỉ phải tính một lần.

Trong triển khai thường gặp, có thể **chỉ cache những trạng thái tight=false**, vì phần hậu tố khi đó không còn phụ thuộc vào giới hạn N tại các vị trí sau. Việc cache tight=true cũng đúng khi bound N cố định và key bao gồm đúng pos,tight,started,rem,prev; nhưng dữ liệu cache đó có thể phụ thuộc vào chính chữ số cận trên của N, nên **không được tái dùng mù** giữa những lần gọi với N khác nhau.

Với bộ điều kiện minh họa, ở pos=k, nếu started=false thì số dựng được là 0 và ta đã định nghĩa 0 là hợp lệ. Với các bài yêu cầu số dương hoặc có đúng k chữ số, base case phải kiểm tra started hoặc số chữ số đã chọn theo hợp đồng riêng.

### Khi nào nên chọn top-down?

Top-down dễ thể hiện các nhánh ràng buộc và hữu ích khi không phải mọi trạng thái đều có thể tới được. Nhưng khi giới hạn N có hàng chục nghìn chữ số, đệ quy sâu theo số chữ số có nguy cơ tràn ngăn xếp Java. Khi đó, **bottom-up lặp theo vị trí** (phần sau) thường đáng tin cậy hơn.

Memoization không có nghĩa có thể gộp hai trạng thái có lịch sử khác nhau mà không chứng minh. Nếu điều kiện cấm cặp chữ số như "13", chỉ nhớ rem mà không nhớ trạng thái mẫu hoặc chữ số trước có thể trả kết quả sai.

## 7. Bottom-up theo chữ số: đếm số tiền tố tới mỗi trạng thái

Thay vì để dfs trả “bao nhiêu cách hoàn thành hậu tố”, ta dùng DP lặp với ý nghĩa khác nhưng tương đương:

~~~text
dp[tight][started][rem][prev]
    = so tien to hop le da duoc dung toi vi tri hien tai
      va co cac thuoc tinh tight, started, rem, prev
~~~

Với một N đã chuẩn hóa (không có số 0 dư ở đầu), trước khi chọn chữ số đầu tiên:

~~~text
dp[1][0][0][10] = 1
tat ca trang thai khac = 0
~~~

Ta chưa chọn gì, nên tiền tố rỗng **bằng** tiền tố rỗng của N (tight=1), chưa bắt đầu số (started=0), tổng chữ số bằng 0 và chưa có chữ số trước (prev=10).

Khi chuyển sang vị trí tiếp theo:

1. Tạo bảng next toàn số 0.
2. Với mỗi trạng thái có số cách c>0:
   - Chọn lần lượt mọi digit từ 0 đến limit.
   - Nếu digit vi phạm điều kiện, bỏ qua.
   - Tính nextTight, nextStarted, nextRem, nextPrev.
   - **Cộng c** vào next[nextTight][nextStarted][nextRem][nextPrev].
3. Gán dp=next rồi xử lý chữ số tiếp.

**Vì sao cần bảng next mới?** Mọi chuyển ở vị trí pos phải đọc trạng thái của **đúng pos chữ số đã xử lý**, chứ không được vô tình sử dụng lại những trạng thái vừa thêm của vị trí pos+1. Đây là cùng lý do trong nhiều bài DP một chiều phải chú ý hướng vòng lặp: không được “dùng một chữ số hai lần”.

### Một ví dụ nhỏ để tự kiểm

Đối với N=20, các số hợp lệ là 0,3,6,9,12,15,18. Ta có:

| Giá trị/nhóm | Đáp án |
| --- | ---: |
| F(0) | 1 |
| F(9) | 4 (0,3,6,9) |
| F(20) | 7 |
| F(99) | 25 |
| F(100) | 25, vì 100 có cặp 0–0 |
| F(250) | 62 |

Ở đây F(N) là số lượng x thỏa cả ba điều kiện và **0≤x≤N**. Dùng vét cạn cho các cận nhỏ này để xác minh chương trình digit DP là cách kiểm thử rất hữu ích.

## 8. Đếm trên một khoảng bằng hiệu hai hàm tiền tố

Phần lớn digit DP đơn giản nhất khi hỏi **từ 0 tới N**. Để đếm trong đoạn đóng [L,R], với 0≤L≤R, đặt:

~~~text
F(N) = so x thoa dieu kien voi 0 <= x <= N

countInRange(L,R) = F(R) - F(L-1)
~~~

Lý do: mọi số thỏa trong [0,R] thuộc đúng một trong hai miền rời nhau [0,L-1] và [L,R]; lấy hiệu loại bỏ phần đầu.

**Biên quan trọng:** nếu L=0 thì **không gọi F(-1)**; kết quả là F(R). Hàm F trong bài chỉ nhận cận không âm. Nếu đề bài cho phép số âm, cần định nghĩa riêng cách xét chữ số của số âm và chuyển bài toán miền âm sang một hoặc nhiều miền không âm, thay vì ném thẳng N âm vào code digit DP không âm.

Ví dụ theo bộ điều kiện xuyên suốt:

~~~text
F(150) - F(39) = 25
countInRange(40,150) = 25

countInRange(7,7) = 0
countInRange(30,30) = 1
countInRange(0,0) = 1
~~~

Cặp cận được coi là **đóng**: bao gồm cả L và R. Nếu đề bài cho [L,R) thì công thức là F(R-1)-F(L-1), phải xử lý các biên và đoạn rỗng phù hợp.

### Vì sao nên nhận cận dưới dạng chuỗi?

Long của Java chỉ biểu diễn tới 9.223.372.036.854.775.807. Nhiều bài digit DP cho cận có hàng chục, hàng trăm chữ số; ta không thể ép vào long. Nhận cận kiểu **chuỗi số thập phân không âm** giúp đọc từng chữ số mà không làm tràn cận.

Để tính L-1, có thể dùng BigInteger(L).subtract(BigInteger.ONE).toString() hoặc viết phép trừ 1 trực tiếp trên chuỗi. Trong ví dụ Java, BigInteger được dùng để làm phép trừ một cách đơn giản. Đếm số cách cũng dùng BigInteger vì chính F(N) có thể vượt long khi N có nhiều chữ số.

**Chuẩn hóa số 0 ở đầu:** "000250" và "250" là cùng một cận; các trạng thái tight phải so với **biểu diễn chuẩn** của giá trị cận. Nếu không chuẩn hóa, DP vẫn có thể đúng với định nghĩa đệm đủ độ dài nhưng cần cẩn thận về điều kiện liên quan độ dài và số 0. Ví dụ Java chuẩn hóa để hợp đồng rõ ràng.

## 9. Java 17 – chương trình digit DP đầy đủ, chạy độc lập

Chương trình này đếm các số nguyên không âm trong [0,N] hoặc [L,R] thỏa đồng thời:

- Không chứa chữ số 7.
- Tổng chữ số chia hết cho 3.
- Không có hai chữ số **thật** kề nhau bằng nhau.
- Số 0 được tính là hợp lệ.

**Thiết kế:** dùng bottom-up, mảng trạng thái BigInteger[2][2][3][11] cho tight, started, remainder, previousDigit. Chỉ số previousDigit=10 là sentinel “chưa có chữ số thật”. Mỗi chữ số của bound tạo một mảng next mới để tránh đọc lẫn trạng thái hai lớp.

Lưu toàn bộ mã trong tệp **DigitPrefixDpDemo.java**:

~~~java
import java.math.BigInteger;
import java.util.Arrays;

public class DigitPrefixDpDemo {
    private static final int MOD = 3;
    private static final int NO_PREV = 10;

    // Tao bang dem moi, tat ca o deu la BigInteger.ZERO.
    private static BigInteger[][][][] zeroStates() {
        BigInteger[][][][] states =
                new BigInteger[2][2][MOD][11];

        for (int tight = 0; tight < 2; tight++) {
            for (int started = 0; started < 2; started++) {
                for (int rem = 0; rem < MOD; rem++) {
                    Arrays.fill(
                            states[tight][started][rem],
                            BigInteger.ZERO);
                }
            }
        }
        return states;
    }

    // Cac can duoc nhap duoi dang chuoi chi gom [0-9].
    private static String normalize(String text) {
        if (text == null || !text.matches("[0-9]+")) {
            throw new IllegalArgumentException(
                    "bound must contain decimal digits only");
        }

        int first = 0;
        while (first + 1 < text.length()
                && text.charAt(first) == '0') {
            first++;
        }
        return text.substring(first);
    }

    // F(N): dem x trong [0,N] thoa ca ba rang buoc.
    static BigInteger countUpTo(String inclusiveUpper) {
        String bound = normalize(inclusiveUpper);

        BigInteger[][][][] dp = zeroStates();
        dp[1][0][0][NO_PREV] = BigInteger.ONE;

        for (int pos = 0; pos < bound.length(); pos++) {
            int boundDigit = bound.charAt(pos) - '0';
            BigInteger[][][][] next = zeroStates();

            for (int tight = 0; tight < 2; tight++) {
                for (int started = 0; started < 2; started++) {
                    for (int rem = 0; rem < MOD; rem++) {
                        for (int prev = 0; prev <= NO_PREV; prev++) {
                            BigInteger count = dp[tight][started][rem][prev];
                            if (count.signum() == 0) {
                                continue;
                            }

                            int limit = tight == 1 ? boundDigit : 9;
                            for (int digit = 0; digit <= limit; digit++) {
                                int nextTight =
                                        tight == 1 && digit == boundDigit
                                                ? 1 : 0;

                                int nextStarted;
                                int nextRem;
                                int nextPrev;

                                if (started == 0 && digit == 0) {
                                    // Chi la so 0 dem o dau.
                                    nextStarted = 0;
                                    nextRem = 0;
                                    nextPrev = NO_PREV;
                                } else {
                                    // Tu day digit la chu so that.
                                    if (digit == 7) {
                                        continue;
                                    }
                                    if (started == 1 && digit == prev) {
                                        continue;
                                    }

                                    nextStarted = 1;
                                    nextRem = (rem + digit) % MOD;
                                    nextPrev = digit;
                                }

                                next[nextTight][nextStarted]
                                        [nextRem][nextPrev] =
                                        next[nextTight][nextStarted]
                                                [nextRem][nextPrev]
                                                .add(count);
                            }
                        }
                    }
                }
            }
            dp = next;
        }

        BigInteger answer = BigInteger.ZERO;
        for (int tight = 0; tight < 2; tight++) {
            // Trang thai chua bat dau = mot so 0 hop le.
            answer = answer.add(dp[tight][0][0][NO_PREV]);

            // Cac so co it nhat mot chu so that va tong mod 3 = 0.
            for (int prev = 0; prev <= 9; prev++) {
                answer = answer.add(dp[tight][1][0][prev]);
            }
        }
        return answer;
    }

    // Doan DONG [lower,upper], chi chap nhan so khong am.
    static BigInteger countRange(String lower, String upper) {
        String l = normalize(lower);
        String r = normalize(upper);
        BigInteger left = new BigInteger(l);
        BigInteger right = new BigInteger(r);

        if (left.compareTo(right) > 0) {
            throw new IllegalArgumentException(
                    "lower must be <= upper");
        }

        BigInteger result = countUpTo(r);
        if (left.signum() == 0) {
            return result; // Khong tinh F(-1).
        }
        return result.subtract(
                countUpTo(left.subtract(BigInteger.ONE).toString()));
    }

    // Chi de kiem chung du lieu nho, khong dung voi can lon.
    private static boolean validSmall(int x) {
        String digits = Integer.toString(x);
        int rem = 0;
        int prev = -1;

        for (int i = 0; i < digits.length(); i++) {
            int digit = digits.charAt(i) - '0';
            if (digit == 7 || digit == prev) {
                return false;
            }
            rem = (rem + digit) % MOD;
            prev = digit;
        }
        return rem == 0;
    }

    static long bruteUpTo(int bound) {
        if (bound < 0 || bound > 100_000) {
            throw new IllegalArgumentException(
                    "brute bound must be in [0,100000]");
        }

        long count = 0;
        for (int x = 0; x <= bound; x++) {
            if (validSmall(x)) {
                count++;
            }
        }
        return count;
    }

    public static void main(String[] args) {
        System.out.println("F(0) = " + countUpTo("0"));
        System.out.println("F(9) = " + countUpTo("9"));
        System.out.println("F(20) = " + countUpTo("20"));
        System.out.println("F(99) = " + countUpTo("99"));
        System.out.println("F(250) = " + countUpTo("250"));
        System.out.println("F(9999) = " + countUpTo("9999"));

        System.out.println("range [40,150] = " +
                countRange("40", "150"));
        System.out.println("range [7,7] = " +
                countRange("7", "7"));
        System.out.println("range [30,30] = " +
                countRange("30", "30"));
        System.out.println("range [0,0] = " +
                countRange("0", "0"));

        System.out.println("leading zeros = " +
                countUpTo("000250"));
        System.out.println("brute F(250) = " +
                bruteUpTo(250));

        try {
            countRange("200", "100");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid range: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac DigitPrefixDpDemo.java
java DigitPrefixDpDemo
~~~

**Stdout chính xác:**

~~~text
F(0) = 1
F(9) = 4
F(20) = 7
F(99) = 25
F(250) = 62
F(9999) = 1567
range [40,150] = 25
range [7,7] = 0
range [30,30] = 1
range [0,0] = 1
leading zeros = 62
brute F(250) = 62
invalid range: lower must be <= upper
~~~

### Giải thích những điểm cài đặt cần chú ý

**zeroStates:** BigInteger là kiểu tham chiếu; nếu không khởi tạo các ô thì giá trị mặc định là null, gọi add/signum sẽ gây NullPointerException. BigInteger.ZERO là đối tượng bất biến, nên dùng Arrays.fill cho nhiều ô là an toàn.

**normalize:** chấp nhận chỉ các chữ số ASCII 0..9 và bỏ các số 0 đứng đầu; giữ lại ít nhất một chữ số cho giá trị 0. Chuỗi rỗng, chuỗi mang dấu trừ, dấu cộng, khoảng trắng hay dấu thập phân đều bị từ chối, tránh âm thầm đổi mô hình số không âm.

**tight:** ở một bước, limit bằng boundDigit khi tight=1 và 9 khi tight=0. nextTight yêu cầu **cả tight hiện tại đúng lẫn digit bằng boundDigit**, để không “trở lại tight” từ tiền tố đã nhỏ hơn.

**started:** nếu chưa bắt đầu và chọn 0 thì rem=0, prev=sentinel 10; nếu đã bắt đầu, số 0 được xử lý là chữ số thật. Trường hợp x=0 duy nhất vẫn được đếm nhờ cộng trạng thái started=0 ở cuối.

**prev:** chỉ kiểm tra chữ số lặp khi started=1; như vậy các số 0 đệm không bị coi là cặp kề nhau. Chữ số 7 bị loại ngay khi là chữ số thật. Giá trị sentinel 10 không thể trùng bất kỳ chữ số 0..9 nào.

**BigInteger:** số cách trong [0,N] không vượt N+1 nhưng N có thể có hàng trăm chữ số; số cách ấy có thể vượt long. BigInteger.add giúp các phép cộng đúng về toán học, không tràn dấu.

**countRange:** dùng công thức F(R)-F(L-1), xử lý L=0 riêng, xác minh 0≤L≤R. Việc dùng BigInteger cho L-1 không gây tràn dù số cận dài.

**bruteUpTo:** chỉ dùng làm đối chứng khi cận nhỏ và hạn chế không quá 100.000. Không nên áp dụng brute force cho N cực lớn, vì khi ấy digit DP mới có giá trị.

### Phân tích độ phức tạp của mã

Với k=độ dài chữ số của N, ta có tối đa:

~~~text
tight     : 2 trang thai
started   : 2 trang thai
remainder : 3 trang thai
prev      : 11 trang thai (0..9 va sentinel 10)
digit     : toi da 10 lua chon moi buoc

so o cho mot lop = 2 * 2 * 3 * 11 = 132
~~~

Một lần xử lý vị trí có tối đa khoảng 132×10 lượt thử chữ số, nên **O(k×2×2×3×11×10)** chuyển trạng thái trong mô hình đơn giá. Bộ nhớ cho hai lớp là O(2×2×3×11) **ô BigInteger**, ngoài chuỗi cận và các giá trị số lớn.

Vì số đếm có thể chứa O(k) bit, BigInteger.add không phải O(1) theo độ dài bit: chi phí bit có thể tăng theo k. Với bộ số trạng thái cố định của bài này, một cách chặn thô là **O(k²) phép toán bit** cho các phép cộng khi k lớn, còn bộ nhớ cho các số lớn có thể tăng **O(k) bit trên mỗi ô**. Đây là chi phí phù hợp hơn khi cận có rất nhiều chữ số. Giới hạn bộ nhớ thực tế còn phụ thuộc đối tượng mảng đa chiều Java và overhead BigInteger.

## 10. Mở rộng ràng buộc: thêm trạng thái gì?

Một cách suy nghĩ hữu ích là bắt đầu từ bộ trạng thái nhỏ nhất: **(pos,tight,started)**. Mỗi ràng buộc bổ sung chỉ nên thêm **thông tin tối thiểu mà các chữ số sau cần biết**.

| Điều kiện trên số đang dựng | Trạng thái bổ sung | Chuyển trạng thái |
| --- | --- | --- |
| Tổng chữ số chia hết cho M | remSum ∈ [0,M) | (remSum + digit) mod M |
| Giá trị số chia hết cho M | remValue ∈ [0,M) | (10×remValue + digit) mod M |
| Có đúng K chữ số khác 0 | countNonzero từ 0..K | Tăng nếu digit thật và khác 0 |
| Không có hai chữ số kề nhau bằng nhau | prevDigit | Loại digit nếu bằng prevDigit thật |
| Chữ số không giảm từ trái sang phải | prevDigit | Sau started, yêu cầu digit≥prevDigit |
| Không xuất hiện chuỗi mẫu cấm | Trạng thái automaton/KMP | Cập nhật theo chữ số, loại trạng thái cấm |
| Đã từng xuất hiện một chữ số chỉ định | seenFlag | OR với điều kiện digit khớp |
| Số chữ số thực bằng đúng K | lengthStarted/count | Chỉ tăng khi digit là chữ số thật |
| Một tiền tố thực phải bằng mẫu P | indexMatched hoặc automaton | Khi bắt đầu số, khớp từng chữ số của P |
| Nhiều điều kiện đồng thời | Tích các trạng thái cần thiết | Kiểm tra tránh bùng nổ trạng thái |

### Remainder của số và remainder của tổng chữ số là hai bài khác nhau

Để kiểm tra **tổng chữ số** mod M, dùng:

~~~text
sumRemNext = (sumRem + digit) % M
~~~

Để kiểm tra **chính giá trị số** mod M, khi thêm chữ số bên phải, dùng:

~~~text
numberRemNext = (numberRem * 10 + digit) % M
~~~

Hai công thức chỉ tình cờ có liên hệ trong một vài modulus; không được dùng một công thức cho mọi câu hỏi. Số 12 có tổng chữ số 3, còn giá trị số 12: mod 5 lần lượt là 3 và 2, khác nhau.

### Đếm chữ số 0 cần started

Nếu muốn đếm số có **đúng hai chữ số 0**, việc tăng bộ đếm khi digit=0 nhưng started=false sẽ tính cả chữ số đệm: chẳng hạn "0009" có ba số 0 đệm nhưng biểu diễn chuẩn là "9", không có chữ số 0 thật.

Nếu chữ số 0 là chữ số đầu tiên và cũng là số duy nhất (x=0), có thể phải cộng **một** chữ số 0 vào bộ đếm khi hoàn tất trạng thái started=false, tùy quy ước đề bài. Đây là lý do base case của các bài digit DP phải được thiết kế theo ngữ nghĩa chính xác thay vì sao chép máy móc.

### Hạn chế về mẫu tiền tố cụ thể

Cần phân biệt hai chữ “tiền tố”:

- **Cờ tight** theo dõi tiền tố số đang xây **so với tiền tố của cận N**.
- **Điều kiện tiền tố nghiệp vụ**, ví dụ “số bắt đầu bằng 12”, là một ràng buộc riêng trên các chữ số **thật**.

Với yêu cầu bắt đầu bằng "12", một state matchedPrefix có thể buộc chữ số thật đầu tiên là 1, chữ số thật thứ hai là 2; sau khi khớp đủ thì cho các chữ số tiếp theo theo quy tắc khác. Leading zeros phải bị bỏ qua trước khi so tiền tố thật; nếu không, số 12 khi đệm thành "0012" sẽ bị từ chối sai.

Nếu yêu cầu không chứa một **mẫu chữ số** bất kỳ như "202", chỉ lưu chữ số trước là không đủ. Có thể xây automaton hữu hạn với trạng thái biểu thị độ dài tiền tố mẫu đã khớp ở cuối chuỗi đang dựng, rồi kết hợp với digit DP.

## 11. Ràng buộc tiền tố tổng quát với automaton

Khi điều kiện mô tả một **ngôn ngữ chính quy** trên biểu diễn thập phân của số (ví dụ cấm chuỗi "13", bắt buộc chứa "25", hoặc số chữ số theo quy luật hữu hạn), ta có thể mô hình hóa bằng **finite-state automaton**.

Ý tưởng:

1. Xây tập trạng thái q của máy tự động, thể hiện phần thông tin lịch sử cần giữ.
2. Với mỗi chữ số thật d, dùng hàm chuyển automaton: qNext=transition(q,d).
3. Khi kết thúc, chỉ nhận những automaton state được phép.
4. Dùng DP trên (pos,tight,started,q), có thể ghép thêm remainder hoặc số lần xuất hiện nếu cần.

Ví dụ để **cấm chuỗi "13"**:

~~~text
q=0 : chu so truoc khong phai 1
q=1 : chu so truoc la 1
q=BAD: da xuat hien "13" (loai ngay)

Neu q=1 va digit=3 -> BAD.
Neu digit=1 -> q=1.
Nguoc lai -> q=0.
~~~

Leading zeros không làm chuyển automaton khi started=false. Với số 103, các chữ số thật là 1,0,3 nên không có "13" liền nhau; với số 132, bước đọc chữ số 3 sau 1 bị loại.

Với nhiều mẫu cấm, có thể dùng automaton từ trie/Aho–Corasick để nhận diện khi vừa chạm một mẫu cấm. Điều kiện này mạnh hơn lưu prev vì một mẫu có thể dài hơn hai chữ số.

### Trạng thái nhân và nguy cơ bùng nổ

Nếu một bài có:

- R trạng thái remainder của số,
- S trạng thái remainder của tổng chữ số,
- P trạng thái automaton,
- K trạng thái đếm số chữ số đặc biệt,

thì số trạng thái tiềm năng mỗi vị trí có thể khoảng 2×2×R×S×P×K. Với mỗi trạng thái lại thử 10 chữ số, tổng chi phí có thể lớn ngay cả khi k chỉ vài chục. Phải ước lượng số trạng thái **trước khi cài đặt**, tránh nối mọi điều kiện thành những chiều DP rất lớn mà không cần.

Có thể giảm trạng thái khi một đại lượng suy ra được từ đại lượng khác, hoặc khi chỉ xét những trạng thái thực sự đạt tới bằng map/memoization thưa; nhưng chứng minh rằng hai trạng thái được gộp thực sự có cùng các lựa chọn hậu tố là điều bắt buộc.

## 12. Đếm, tối ưu và tính tổng khác nhau thế nào?

DP của bài đang lưu **số lượng tiền tố hợp lệ**. Nếu thay yêu cầu, phép chuyển và giá trị trạng thái phải thay đổi tương ứng.

### Đếm số lượng

Trạng thái lưu count; mỗi tiền tố có c cách thì mọi chuyển hợp lệ từ nó đóng góp thêm c cách. Kết quả là tổng các trạng thái được chấp nhận ở cuối. Đây là dạng dùng nhiều nhất để trả lời “bao nhiêu số thỏa”.

### Tính tổng giá trị các số hợp lệ

Muốn tính **tổng các số x thỏa điều kiện**, chỉ lưu count chưa đủ. Có thể lưu hai đại lượng cho mỗi trạng thái:

- cnt: số tiền tố đạt trạng thái.
- sum: tổng các **giá trị số của tiền tố** đó.

Nếu thêm chữ số digit vào bên phải, mỗi số tiền tố x biến thành 10x+digit. Do vậy:

~~~text
nextCnt += cnt
nextSum += 10 * sum + digit * cnt
~~~

Cần xử lý leading zeros và điều kiện chấp nhận cuối giống phần đếm. Công thức vẫn đúng với biểu diễn có đệm 0 đầu vì thêm 0 vào một tiền tố số 0 cho giá trị 0; nhưng ràng buộc **số chữ số thật** vẫn cần started.

Nếu câu hỏi là **tổng chữ số của các số hợp lệ**, thì phép cộng có dạng:

~~~text
nextDigitSum += priorDigitSum + digit * cnt
~~~

Chỉ cộng chữ số thật khi mô hình yêu cầu. Đây là một dạng DP mang **giá trị tổng hợp**, không chỉ đếm số cách.

### Tối ưu và dựng một số cụ thể

Nếu muốn tìm số lớn nhất ≤N thỏa điều kiện, có thể dùng DP Boolean có/không tồn tại một hậu tố hợp lệ rồi dựng đáp án từ trái sang phải, chọn chữ số lớn nhất vẫn có khả năng hoàn tất. Không thể đơn thuần đổi phép cộng của bài đếm thành max mà bỏ qua trạng thái tồn tại và cấu trúc chữ số; phải chứng minh quy tắc dựng vẫn đáp ứng tight và điều kiện phụ.

Nếu cần tìm **tất cả số**, bản thân số lượng đầu ra có thể rất lớn. Digit DP giúp tính kết quả tổng hợp mà không phải liệt kê các số, nhưng không thể tránh chi phí xuất nếu yêu cầu liệt kê từng số.

## 13. Chứng minh tính đúng của digit DP

**Mệnh đề:** sau khi duyệt pos chữ số của bound B, dp[tight][started][rem][prev] bằng số chuỗi tiền tố độ dài pos **không vượt tiền tố tương ứng của B** và thỏa mọi ràng buộc đã xét, có đúng thông tin tóm tắt tight,started,rem,prev.

**Cơ sở:** với pos=0, có đúng một tiền tố rỗng. Nó bằng tiền tố rỗng của B, chưa bắt đầu số, tổng chữ số modulo 3 bằng 0 và chưa có chữ số thật. Vì vậy dp[1][0][0][10]=1, các trạng thái khác bằng 0.

**Bước quy nạp:** giả sử mọi count của lớp pos đúng. Với một tiền tố hợp lệ được đếm trong một trạng thái:

1. Mọi chữ số tiếp theo của một số không vượt B phải nằm trong 0..boundDigit nếu tight=true, hoặc 0..9 nếu tight=false. Vòng lặp xét **đầy đủ và chỉ** các chữ số hợp lệ theo cận.
2. Các nhánh bắt đầu số, chữ số cấm và chữ số kề nhau được kiểm tra theo đúng tiền tố đã chọn. Không có nhánh sai nào được chuyển tiếp.
3. Mỗi chữ số d tạo một tiền tố dài pos+1 duy nhất; hai đường chuyển từ các tiền tố/ chữ số khác nhau không biểu diễn cùng **chuỗi chữ số độ dài pos+1**, nên phép cộng đếm không trùng.
4. Thông tin tight,started,rem,prev sau chuyển được cập nhật theo định nghĩa trạng thái, đủ để quyết định phần tiếp theo.

Mọi tiền tố hợp lệ độ dài pos+1 có đúng một tiền tố cha độ dài pos và một chữ số cuối d; vì vòng lặp đã xét cha và d đó nên không bỏ sót. Vậy các count ở lớp pos+1 đúng.

**Kết thúc:** mỗi số x trong [0,N] có đúng một biểu diễn k chữ số đệm 0 ở đầu, nên có đúng một đường đi trong DP. Các nhánh vi phạm bị loại; các nhánh còn lại có rem=0 được nhận. Trạng thái chưa bắt đầu đại diện duy nhất cho số 0, vốn hợp lệ theo quy ước. Vì thế tổng count của các trạng thái được chấp nhận bằng F(N) chính xác.

**Đếm khoảng:** vì [0,R] là hợp rời nhau của [0,L-1] và [L,R] khi 0<L≤R, F(R)-F(L-1) đúng; với L=0, F(R) đúng trực tiếp.

Đây là khung chứng minh có thể tái dùng cho nhiều bài digit DP, với điều kiện phải sửa phần trạng thái và cơ sở theo chính ràng buộc mới.

## 14. Sai sót thường gặp và dấu hiệu nhận biết

| Sai sót | Hậu quả | Cách sửa |
| --- | --- | --- |
| Xét từng số tới N≈10^18 | Quá chậm | Dùng DP theo độ dài biểu diễn chữ số |
| Quên tight | Đếm cả số vượt cận N | Ràng buộc chữ số khi prefix còn bằng N |
| Đặt nextTight chỉ dựa trên digit | Tiền tố đã nhỏ hơn có thể “trở lại tight” sai | nextTight = tight AND digit==boundDigit |
| Lấy limit=boundDigit cả khi tight=false | Đếm thiếu | Khi đã nhỏ hơn, cho phép 0..9 |
| Xem số 0 đệm là chữ số thật | Đếm nhầm số 0, lặp chữ số hoặc độ dài | Dùng started và sentinel |
| Không xét số 0 ở trạng thái cuối | Off-by-one khi 0 hợp lệ | Quy định riêng trường hợp all-leading-zero |
| Đếm 0 là số dương | Sai khi đề chỉ cho x≥1 | Chỉ nhận started=true nếu loại 0 |
| Quên reset next theo từng vị trí | Dùng trạng thái cũ và mới lẫn nhau | Tạo bảng next mới và gán dp=next |
| Sai công thức mod giá trị số | Nhầm tổng chữ số với chính số | Giá trị số: (10×rem+digit) mod M |
| Không lưu prev khi ràng buộc kề nhau | Đếm cả các số có 00,11,... thật | Thêm last digit vào state |
| Dùng charAt cho mọi ngôn ngữ số | Nhầm chữ số Unicode hoặc định dạng khác | Đặc tả ASCII decimal [0-9] rõ ràng |
| Tính F(L-1) với L=0 | Cận âm không hợp lệ | Trả F(R) trực tiếp |
| Dùng long cho số lượng quá lớn | Tràn và có thể âm | Dùng BigInteger hoặc modulo theo đề |
| Cache tight=true giữa các bound khác nhau | Kết quả phụ thuộc bound cũ | Cache theo bound hoặc chỉ reuse trạng thái độc lập cận |
| Dùng đệ quy quá sâu | StackOverflowError trên chuỗi rất dài | Dùng bottom-up theo chữ số |
| Ghép quá nhiều chiều trạng thái | Bùng nổ thời gian/bộ nhớ | Tính trước tích số trạng thái; nén thông tin dư |

**Mẫu kiểm tra rất nhạy:** với N=20, bộ điều kiện ví dụ phải cho **7** (gồm số 0). Với N=100, F(100)=F(99)=25 vì 100 có hai chữ số 0 thật kề nhau. Nếu kết quả khác, hãy kiểm tra started và prev trước.

## 15. Bộ kiểm thử và bài tập

### Các ca kiểm thử biên

| Câu hỏi | Kỳ vọng | Lý do |
| --- | ---: | --- |
| F(0) | 1 | Số 0 hợp lệ |
| F(9) | 4 | 0,3,6,9 |
| F(20) | 7 | 0,3,6,9,12,15,18 |
| F(99) | 25 | Đối chứng vét cạn |
| F(100) | 25 | 100 có 00 thật liên tiếp |
| F(250) | 62 | Đối chứng vét cạn |
| F(9999) | 1567 | Kiểm soát thêm nhiều chữ số |
| [40,150] | 25 | Hiệu F(R)-F(L-1) |
| [7,7] | 0 | Chữ số bị cấm |
| [30,30] | 1 | 3+0 chia hết 3, không có 7 hoặc cặp bằng nhau |
| [0,0] | 1 | Xử lý L=0 |
| F("000250") | 62 | Chuẩn hóa cận có số 0 đầu |
| Cận là chuỗi rỗng, âm hoặc có ký tự khác chữ số | Từ chối | Hợp đồng chỉ nhận thập phân không âm |
| [200,100] | Từ chối | L>R |

### Kiểm thử tự động bằng tính chất

1. **Đối chiếu brute force:** với mọi N từ 0 tới 1.000, xác minh F(N) bằng số x từ 0..N thỏa điều kiện kiểm tra trực tiếp.
2. **Tính đơn điệu:** vì F đếm các số không âm hợp lệ, F(N+1)≥F(N) với mọi N≥0. Nếu dùng modulo thì **phần dư** không còn nhất thiết đơn điệu.
3. **Độ tăng tối đa một:** F(N+1)-F(N) bằng 1 nếu N+1 hợp lệ, ngược lại 0. Đây là oracle mạnh vì mỗi bước thêm đúng một số mới.
4. **Kết quả khoảng:** countRange(L,R) bằng F(R)-F(L-1) khi L>0, và bằng F(R) khi L=0.
5. **Ghép khoảng:** với L≤M<R, countRange(L,R)=countRange(L,M)+countRange(M+1,R).
6. **Không âm:** countRange(L,R)≥0 với mọi 0≤L≤R.
7. **Định dạng cận:** F("000" nối N)=F(N) sau khi chuẩn hóa cùng giá trị.
8. **Chữ số bị cấm:** không số nào trong danh sách sinh bằng brute force có chữ số 7.
9. **Leading zeros:** số có các số 0 đệm không được đánh giá như có chữ số 0 thật ở phía trước.
10. **Số cực lớn:** chỉ kiểm tra một số tính chất cấu trúc (ví dụ F(N)≤N+1 và không âm) bằng BigInteger nếu vét cạn không khả thi.

### Bài tập tự luyện

1. Với N=250, lập bảng cách cập nhật tight cho các tiền tố 1, 23, 25 và 251. Vì sao tiền tố 251 không được đi tới trạng thái DP hợp lệ?
2. Giữ nguyên điều kiện cấm chữ số 7 và tổng chữ số mod 3, nhưng **bỏ điều kiện hai chữ số kề nhau bằng nhau**. Xác định những chiều trạng thái nào có thể bỏ đi, và cập nhật code.
3. Thay điều kiện tổng chữ số chia hết cho 3 bằng **chính giá trị số chia hết cho 7**. Viết công thức remainder đúng và thử N nhỏ bằng brute force.
4. Đếm số trong [L,R] có **đúng hai chữ số 0 thật**. Giải thích cách xử lý leading zeros và số 0 theo định nghĩa mới; không được cộng 0 đệm vào bộ đếm.
5. Đếm số có **chữ số không giảm** từ trái sang phải. Thêm prev và điều kiện digit≥prev sau khi started=true, và kiểm thử các số có chữ số lặp nếu đề cho phép.
6. Với điều kiện “số bắt đầu bằng tiền tố 12”, hãy thiết kế trạng thái theo tiến độ khớp tiền tố thật. Vì sao không thể chỉ nhìn cờ tight để biết số bắt đầu bằng 12?
7. Xây automaton ba trạng thái để cấm mẫu liền nhau "13"; kết hợp với tight và started. Kiểm thử 132 bị loại nhưng 103 không bị loại.
8. Mở rộng trạng thái từ count sang (count,sumOfNumbers), viết công thức nextSum += 10×sum + digit×count và tính tổng các số trong [0,100] bằng brute force để kiểm chứng.
9. So sánh top-down memo với bottom-up khi N có 100.000 chữ số. Phân tích stack, số trạng thái và chi phí số lớn thay vì chỉ đo số lời gọi.
10. Viết bộ kiểm thử tự động trên mọi N≤10.000: đối chiếu kết quả F(N) digit DP với brute force tăng dần, kiểm tra độ tăng 0/1 và các khoảng ngẫu nhiên.
11. Nếu đề chỉ yêu cầu số **dương** thỏa điều kiện, thay đổi chính xác phần nào ở bước kết thúc để loại 0 mà không ảnh hưởng các số có leading zeros?
12. Khi điều kiện là “không chứa mẫu 202”, giải thích vì sao chỉ nhớ prevDigit không đủ và cần automaton hoặc bộ nhớ của hậu tố khớp một phần với mẫu.

**Kết luận:** digit DP là cách **gộp các tiền tố chữ số có cùng thông tin liên quan đến tương lai**. Cờ tight kiểm soát không vượt cận, started phân biệt chữ số đệm và chữ số thật, các chiều như remainder/prev/automaton mô tả điều kiện nghiệp vụ. Với một hàm F(N) đếm [0,N], kết quả khoảng là **F(R)-F(L-1)** và phải xử lý L=0. Một bài digit DP đúng cần định nghĩa trạng thái, chuyển trạng thái, điều kiện nhận ở cuối, kiểu số đủ lớn và kiểm thử kỹ các ranh giới.

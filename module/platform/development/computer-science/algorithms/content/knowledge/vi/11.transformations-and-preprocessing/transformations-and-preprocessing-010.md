# Dấu vân tay dữ liệu, va chạm băm và bước xác minh

## 1. Bài toán: nhận diện nhanh không đồng nghĩa chứng minh giống nhau

Khi xử lý nhiều chuỗi, tệp hoặc đoạn dữ liệu, ta thường muốn trả lời: “Hai đối tượng này có bằng nhau không?”, “Một mẫu có xuất hiện trong văn bản không?”, hoặc “Những đối tượng nào đáng kiểm tra là trùng lặp?”. So sánh toàn bộ nội dung có thể tốn thời gian nếu đối tượng dài và số cặp ứng viên lớn. Một cách phổ biến là tính trước **dấu vân tay dữ liệu (fingerprint)**: một giá trị ngắn đại diện cho nội dung.

Ví dụ:

~~~text
Dữ liệu A ──> hàm băm ──> dấu vân tay h(A)
Dữ liệu B ──> hàm băm ──> dấu vân tay h(B)

h(A) khác h(B)  ──> A và B chắc chắn khác nhau,
                      nếu dùng cùng cách biểu diễn và hàm băm.
h(A) bằng h(B) ──> A, B có thể giống nhau;
                      phải xác minh nội dung nếu cần kết luận chính xác.
~~~

Bước băm là **bộ lọc ứng viên**, không phải phép chứng minh hai nội dung giống hệt. Với miền dữ liệu có nhiều khả năng hơn số giá trị băm, **va chạm băm (hash collision)** không thể loại bỏ hoàn toàn.

Chủ đề này nằm trong nhóm **biến đổi và tiền xử lý**: ta biến dữ liệu dài thành giá trị dễ so sánh để giảm số lần kiểm tra đắt tiền, sau đó dùng phép đối chiếu chính xác khi cần. Tư duy “băm trước, xác minh sau” xuất hiện trong Rabin–Karp, tìm chuỗi, khử trùng lặp, bảng băm và nhiều hệ thống lập chỉ mục.

## 2. Hợp đồng và các khái niệm phải phân biệt

Đầu tiên phải xác định **chính xác thế nào là cùng dữ liệu**. Hai chuỗi có thể giống về mặt hiển thị nhưng khác chuỗi mã hóa Unicode; hai tệp có thể trông giống nhau nhưng có byte khác nhau. Đối với bài toán so khớp chuỗi Java trong ví dụ, ta chọn hợp đồng:

- Đầu vào gồm text và pattern là các đối tượng String không null.
- Một lần xuất hiện là **dãy đơn vị mã UTF-16 bằng nhau theo thứ tự**, có phân biệt chữ hoa/chữ thường; không tự chuẩn hóa Unicode.
- Trả chỉ số bắt đầu nhỏ nhất, đếm từ 0 theo chỉ số char của Java, nếu tìm thấy; trả −1 nếu không.
- Mẫu rỗng khớp tại vị trí 0, kể cả khi văn bản rỗng.
- Không sửa dữ liệu; không cần tạo mọi chuỗi con.
- Băm chỉ được dùng để chọn vị trí cần kiểm tra; **chỉ phép so sánh từng ký tự mới quyết định có khớp**.

Một số thuật ngữ:

| Thuật ngữ | Nghĩa |
| --- | --- |
| Dữ liệu gốc | Chuỗi, byte hoặc bản ghi cần so sánh |
| Hàm băm H | Phép ánh xạ xác định từ nội dung sang một miền giá trị hữu hạn |
| Fingerprint | Giá trị H(data) dùng để nhận diện sơ bộ |
| Va chạm | Hai nội dung khác nhau A≠B nhưng H(A)=H(B) |
| Ứng viên | Cặp/đoạn có fingerprint phù hợp, cần kiểm tra sâu |
| Xác minh chính xác | So sánh biểu diễn nội dung đã định nghĩa, byte-by-byte hoặc ký tự-by-ký tự |
| False positive do băm | Băm bằng nhau khiến ta nghi ngờ trùng, nhưng nội dung khác |
| False negative khi lọc bằng băm | Nếu dữ liệu **thực sự bằng nhau** và băm đúng cùng cách thì không xảy ra; nếu xảy ra, có lỗi triển khai hoặc chuẩn hóa không nhất quán |

Một cách xây dựng đúng phải bảo đảm: **nội dung bằng nhau ⇒ fingerprint bằng nhau**. Chiều ngược lại thường không đúng. Nếu cần so sánh dữ liệu về mặt ngữ nghĩa, hãy định nghĩa cách chuẩn hóa trước khi băm, đồng thời xác minh trên cùng biểu diễn chuẩn hóa đó.

## 3. Vì sao va chạm là điều không thể tránh?

Giả sử hàm băm trả về một số trong miền có M giá trị, ví dụ các số từ 0 đến M−1. Nếu có nhiều hơn M dữ liệu đầu vào khác nhau, **nguyên lý Dirichlet (pigeonhole principle)** bảo đảm phải tồn tại ít nhất hai đầu vào khác nhau có cùng giá trị băm.

~~~text
H: miền dữ liệu rất lớn ──> {0, 1, ..., M-1}

Có M+1 đầu vào phân biệt nhưng chỉ M ô đầu ra:
ít nhất một ô chứa dấu vân tay của hai đầu vào khác nhau.
~~~

Đây là giới hạn toán học, không phải lỗi riêng của một thư viện. Với băm 32-bit có tối đa 2³² dấu vân tay, còn số chuỗi khả dĩ là lớn hơn rất nhiều. Ngay cả fingerprint dài 256 bit cũng vẫn có miền đầu ra hữu hạn: va chạm vẫn tồn tại về mặt toán học, chỉ khác ở mức khó tìm hoặc xác suất xảy ra với dữ liệu ngẫu nhiên theo mô hình phù hợp.

### Ví dụ va chạm minh họa có thể tính tay

Xét một hàm băm đồ chơi cho chuỗi hai ký tự ASCII:

~~~text
H(s0 s1) = (31 * mã(s0) + mã(s1)) mod 101

H("aZ") = (31 * 97 + 90) mod 101
         = 3097 mod 101 = 67

H("b;") = (31 * 98 + 59) mod 101
         = 3097 mod 101 = 67
~~~

Hai chuỗi **"aZ" và "b;" khác nhau**, nhưng dấu vân tay đều là 67. Đây là một **va chạm thực sự** trong hàm băm đồ chơi (base 31, mod 101). Hàm băm rolling trong chương trình Java sau sẽ dùng **tham số khác** để minh họa cách triển khai ở quy mô hợp lý hơn; không được suy ra hai chuỗi trên nhất thiết va chạm dưới mọi hàm băm.

**Quan trọng:** một fingerprint bằng nhau không chứng minh trùng nội dung, dù đó là CRC, hashCode của Java, rolling hash, hay digest mạnh. Nếu đầu ra của hệ thống đòi **tính đúng tuyệt đối**, phải so sánh dữ liệu thật hoặc dựa vào một biểu diễn đã được chứng minh không va chạm trong miền đầu vào đã giới hạn.

## 4. Hai bước: lọc bằng dấu vân tay rồi xác minh

Chiến lược tổng quát:

1. **Tiền xử lý:** tính fingerprint cho mẫu hoặc các đối tượng cần truy vấn. Với dữ liệu dạng cửa sổ trượt, có thể dùng rolling hash để cập nhật nhanh từ cửa sổ trước.
2. **Lọc:** so giá trị fingerprint. Nếu khác, bỏ ứng viên ngay; hai nội dung bằng nhau không thể cho hai fingerprint khác nhau dưới cùng quy tắc băm.
3. **Xác minh:** nếu fingerprint bằng nhau, so từng ký tự/byte của hai nội dung theo hợp đồng.
4. **Kết luận:** chỉ khi xác minh thành công mới công nhận bằng nhau; khi xác minh thất bại, ghi nhận một ứng viên dương tính giả và tiếp tục tìm.

~~~text
                   fingerprint ứng viên
                           |
                           v
                 Có bằng fingerprint mẫu?
                        /        \
                      Không       Có
                       |          |
                       v          v
                    Bỏ qua      So nội dung gốc
                                     /      \
                                   Khác     Bằng
                                    |        |
                                    v        v
                                Bỏ qua   Xác nhận khớp
~~~

Đây là kiểu **filter-and-verify**. Việc chọn fingerprint có thể làm giảm số ứng viên cần so sánh đầy đủ, nhưng không được loại bỏ bước so chính xác nếu mục tiêu là tìm sự giống nhau tuyệt đối.

### Ví dụ trong khử trùng lặp tệp

Một hệ thống có thể nhóm các tệp theo (kích thước, fingerprint). Nếu kích thước khác nhau thì chắc chắn byte khác nhau. Nếu kích thước và fingerprint đều bằng nhau, cần đọc và đối chiếu byte thật để khẳng định trùng, trước khi xóa bản sao hoặc cập nhật dữ liệu quan trọng. Trường hợp chỉ lưu digest mà không còn nội dung gốc thì **không thể xác minh tuyệt đối bằng dữ liệu đã mất**; chỉ có thể nói mức tin cậy theo loại digest và mô hình rủi ro.

Tương tự, một HashMap có thể dùng giá trị hashCode để tìm **bucket**, nhưng phép nhận biết khóa bằng nhau còn phụ thuộc equals. Trùng hashCode không có nghĩa hai khóa là cùng đối tượng hay có cùng nội dung.

## 5. Dấu vân tay đa thức cho chuỗi

Để có một fingerprint **phụ thuộc thứ tự ký tự**, dùng hàm băm đa thức:

~~~text
H(s[0..m)) =
    (s[0] * B^(m-1)
   + s[1] * B^(m-2)
   + ...
   + s[m-1]) mod P
~~~

Trong đó:

- m là độ dài chuỗi theo đơn vị mã đang xét.
- s[i] là mã số của ký tự tại vị trí i.
- B là cơ số dương, ví dụ 65.537.
- P là mô-đun nguyên dương, ví dụ 1.000.000.007.
- Kết quả trong [0, P−1] được lưu bằng kiểu long trong Java.

Cũng có thể tính liên tiếp bằng công thức Horner:

~~~text
h = 0
for each codeUnit c:
    h = (h * B + c) mod P
~~~

Chọn B lớn hơn giá trị char tối đa 65.535 làm cách biểu diễn trước khi lấy mod dễ hiểu hơn, dù **không loại trừ va chạm sau modulo**. Mọi phép tính cần dùng kiểu đủ rộng: với B=65.537 và P=1.000.000.007, tích của một phần dư nhỏ hơn P với B nằm trong giới hạn long, nên không xảy ra tràn long trong những phép nhân này.

Một số băm còn dùng nhiều mô-đun để giảm xác suất va chạm trong các mô hình phù hợp. Hai hash độc lập hoặc gần độc lập giảm rủi ro nhưng **không tạo bằng chứng tuyệt đối**; đối với yêu cầu chính xác, phép xác minh nội dung vẫn là điều quyết định.

## 6. Rolling hash: cập nhật dấu vân tay của cửa sổ kế tiếp

Khi tìm mẫu dài m trong văn bản dài n, ta cần kiểm tra các cửa sổ liên tiếp có độ dài m:

~~~text
text:    z z a b a c a b a
window:  [z z a]
          [z a b]
            [a b a]  <-- khớp mẫu "aba" tại 2
              ...
~~~

Nếu băm mỗi cửa sổ từ đầu, riêng việc tính hash đã có thể tốn O((n−m+1)·m). **Rolling hash** tránh tính lại toàn bộ cửa sổ khi trượt sang phải một ký tự.

Gọi oldHash là dấu vân tay của cửa sổ dài m, oldFirst là mã ký tự đầu, newLast là mã ký tự mới đi vào. Đặt:

~~~text
power = B^(m-1) mod P

removed = (oldHash - oldFirst * power) mod P
newHash = (removed * B + newLast) mod P
~~~

Ta loại hạng tử trọng số cao nhất, nhân B để dịch các hạng tử còn lại sang trái một bậc, rồi cộng mã ký tự mới. Mỗi lần trượt chỉ cần **O(1)** phép toán số nguyên dưới mô hình đang dùng.

Với số âm khi trừ modulo, trong Java tính:

~~~java
windowHash = (windowHash - outgoing + MOD) % MOD;
windowHash = (windowHash * BASE + incoming) % MOD;
~~~

Nếu oldHash và outgoing đều nằm trong [0, MOD−1], cộng thêm MOD làm giá trị trước phép % không âm. Đây là một chi tiết quan trọng: Java dùng phép chia lấy dư có thể cho số âm nếu toán hạng âm, nên không nên quên chuẩn hóa.

### Rabin–Karp: băm để sàng lọc, so sánh để xác nhận

Thuật toán tìm chuỗi Rabin–Karp phù hợp để minh họa:

- Tính H(pattern) một lần và H(cửa sổ đầu) một lần.
- Duyệt các vị trí bắt đầu cửa sổ từ trái sang phải.
- Nếu hai hash khác nhau, chắc chắn cửa sổ không bằng pattern.
- Nếu hai hash bằng nhau, dùng phép so sánh ký tự chính xác.
- Nếu chưa khớp, cập nhật hash cửa sổ kế tiếp bằng công thức rolling.

Lưu ý đây là **tìm kiếm chính xác** chứ không phải tìm chuỗi “gần giống”. Nếu muốn tìm bản ghi tương tự về ngữ nghĩa, cần một định nghĩa độ tương tự khác (ví dụ khoảng cách chỉnh sửa hoặc kỹ thuật phân cụm) và không thể mặc nhiên dùng đồng nhất hash làm độ tương tự.

## 7. Truy vết trên ví dụ cụ thể

Cho text = "zzabacaba", pattern = "aba", m=3.

| start | Cửa sổ | Kết quả sau lọc | Quyết định |
| ---: | --- | --- | --- |
| 0 | zza | Không cùng nội dung mẫu | Chưa khớp; tiếp tục |
| 1 | zab | Không cùng nội dung mẫu | Chưa khớp; tiếp tục |
| 2 | aba | Hash bằng và ký tự bằng | Trả chỉ số 2 |

Ở start=2, ba mã ký tự giống nhau theo thứ tự nên hash cũng giống nhau; việc so chính xác xác nhận một lần xuất hiện. Hàm trả **chỉ số đầu tiên** vì duyệt từ trái sang phải, không dừng ở một ứng viên hash bằng nhưng dữ liệu khác.

Cần phân biệt hai loại số đo:

- **Số cửa sổ có thể xét** khi m>0 và m≤n là n−m+1.
- **Số lần xác minh thực tế** phụ thuộc dữ liệu và chất lượng hash. Không được bịa số lần so sánh chính xác hay thời gian chạy trên một máy nếu chưa thực sự đo.

Đối với pattern rỗng, trong ví dụ Java ta áp dụng hợp đồng tương tự String.indexOf: trả vị trí 0 và không tạo cửa sổ độ dài 0 để rolling. Khi m>n, trả −1 ngay vì không có cửa sổ đủ dài.

## 8. Java 17+: chương trình Rabin–Karp có xác minh chính xác

Chương trình dưới đây **chạy độc lập** và không dùng thư viện bên ngoài. Mục tiêu là tìm lần xuất hiện **đầu tiên** của pattern trong text theo đơn vị mã UTF-16 của Java. Mẫu rỗng trả 0; đầu vào null gây NullPointerException. Hash dùng một mô-đun; va chạm chỉ làm tăng số lần xác minh, **không làm trả vị trí sai**, vì mọi ứng viên đều phải vượt phép so ký tự.

Lưu tệp **FingerprintVerification.java**:

~~~java
import java.util.Objects;

public final class FingerprintVerification {
    private static final long MOD = 1_000_000_007L;
    private static final long BASE = 65_537L;

    private FingerprintVerification() {}

    /**
     * Returns the first UTF-16 starting index of pattern in text.
     * Returns -1 when absent. Empty pattern matches at index 0.
     * Hash equality is always followed by exact character comparison.
     */
    public static int indexOf(String text, String pattern) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(pattern, "pattern");

        int n = text.length();
        int m = pattern.length();

        if (m == 0) {
            return 0;
        }
        if (m > n) {
            return -1;
        }

        long highestPower = 1L;
        for (int i = 1; i < m; i++) {
            highestPower = (highestPower * BASE) % MOD;
        }

        long patternHash = 0L;
        long windowHash = 0L;
        for (int i = 0; i < m; i++) {
            patternHash =
                    (patternHash * BASE + pattern.charAt(i)) % MOD;
            windowHash =
                    (windowHash * BASE + text.charAt(i)) % MOD;
        }

        for (int start = 0; start <= n - m; start++) {
            if (windowHash == patternHash
                    && equalsAt(text, pattern, start)) {
                return start;
            }

            // Advance to next window only if one exists.
            if (start < n - m) {
                long outgoing =
                        (text.charAt(start) * highestPower) % MOD;
                windowHash = (windowHash - outgoing + MOD) % MOD;
                windowHash =
                        (windowHash * BASE + text.charAt(start + m)) % MOD;
            }
        }
        return -1;
    }

    private static boolean equalsAt(
            String text, String pattern, int start) {
        for (int i = 0; i < pattern.length(); i++) {
            if (text.charAt(start + i) != pattern.charAt(i)) {
                return false;
            }
        }
        return true;
    }

    // Deliberately weak toy hash to exhibit a real collision.
    private static long toyHash(String value) {
        long hash = 0L;
        for (int i = 0; i < value.length(); i++) {
            hash = (hash * 31L + value.charAt(i)) % 101L;
        }
        return hash;
    }

    public static void main(String[] args) {
        System.out.println("First match: "
                + indexOf("zzabacaba", "aba"));
        System.out.println("Absent: "
                + indexOf("zzabacaba", "xyz"));
        System.out.println("Empty pattern: "
                + indexOf("abc", ""));
        System.out.println("Pattern longer: "
                + indexOf("ab", "abc"));
        System.out.println("Repeated: "
                + indexOf("aaaaa", "aaa"));

        // Java String indices count UTF-16 code units.
        System.out.println("Unicode: "
                + indexOf("A😀B😀", "😀B"));

        System.out.println("Toy hashes: "
                + toyHash("aZ") + ", " + toyHash("b;"));
        System.out.println("Toy strings equal: "
                + "aZ".equals("b;"));

        try {
            indexOf(null, "a");
        } catch (NullPointerException ex) {
            System.out.println("Null: NullPointerException");
        }
    }
}
~~~

Biên dịch mã nguồn được lưu bằng UTF-8 và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 FingerprintVerification.java
java FingerprintVerification
~~~

Stdout dự kiến:

~~~text
First match: 2
Absent: -1
Empty pattern: 0
Pattern longer: -1
Repeated: 0
Unicode: 1
Toy hashes: 67, 67
Toy strings equal: false
Null: NullPointerException
~~~

Hai chuỗi "aZ" và "b;" trong phần toyHash **không bằng nhau**, dù có cùng hash 67; phép equals trả false. Đây là ví dụ trực tiếp cho lý do **không được kết luận hai dữ liệu bằng nhau từ hash**. Mẫu "😀B" nằm từ chỉ số char 1 của chuỗi "A😀B😀": emoji chiếm **hai đơn vị mã UTF-16**, nên chỉ số trả về theo String không phải luôn là số ký tự Unicode người dùng nhìn thấy.

**Phạm vi an toàn số học:** mọi hash đều nằm trong [0, MOD−1]. Với BASE=65.537 và MOD=1.000.000.007, tích lớn nhất trong update nhỏ hơn khoảng 6,6×10¹³, nhỏ hơn rất nhiều giới hạn long có dấu. Trước phép modulo sau khi loại ký tự cũ, biểu thức đã được cộng thêm MOD, nên không âm theo các giới hạn vừa nêu.

## 9. Bất biến và chứng minh tính đúng

Đặt H(S) là hash đa thức của chuỗi S độ dài m trên cùng mô-đun, cơ số và quy ước ký tự.

### 9.1. Bất biến rolling hash

Ở đầu mỗi vòng lặp với chỉ số start, windowHash **bằng H(text[start..start+m))** và patternHash bằng H(pattern). Đúng tại start=0 vì hai hash được tính từ đầu. Nếu chưa phải cửa sổ cuối, phép trừ hạng tử đầu, nhân BASE rồi cộng ký tự mới đúng bằng công thức H của cửa sổ dịch phải một đơn vị; lấy modulo duy trì cùng giá trị phần dư. Vì vậy bất biến đúng ở vòng tiếp theo.

### 9.2. Không bỏ qua kết quả thật

Nếu một cửa sổ **thực sự bằng** pattern theo từng đơn vị mã, hai chuỗi có cùng độ dài và cùng thứ tự mã, nên H(cửa sổ)=H(pattern). Do đó **điều kiện hash bằng không thể loại bỏ một khớp thật**, miễn hàm băm và rolling được triển khai đúng. Khi hash bằng, equalsAt sẽ trả true cho cửa sổ ấy.

Nếu hash khác, cửa sổ chắc chắn không bằng pattern, nên bỏ qua là an toàn. Nếu hash bằng nhưng equalsAt trả false, đó là một va chạm tại cửa sổ, và bỏ qua cũng đúng vì dữ liệu thật khác.

### 9.3. Kết quả là khớp đầu tiên

Các giá trị start được xét lần lượt 0, 1, 2,..., n−m. Khi trả start, hàm đã kiểm tra mọi vị trí trước đó mà không tìm thấy khớp chính xác; vì vậy đây là vị trí đầu tiên. Nếu duyệt hết mà không có vị trí nào được xác minh, trả −1 là đúng. Vòng lặp hữu hạn và mỗi bước tăng start nên luôn kết thúc.

Đối với m=0 hoặc m>n, hàm xử lý riêng theo hợp đồng ngay đầu phương thức, không dựa vào bất biến cửa sổ độ dài m dương.

**Hệ quả:** va chạm hash chỉ có thể làm tăng chi phí xác minh, không làm mất hoặc tạo ra một kết quả khớp sai ở chương trình này. Bằng chứng nằm ở bước so dữ liệu, không nằm ở giả định hash “đủ tốt”.

## 10. Phân tích độ phức tạp đúng theo số ứng viên

Gọi n=text.length(), m=pattern.length() theo đơn vị mã UTF-16, giả định m>0, m≤n.

- Tính highestPower=B^(m−1) mod P: Θ(m).
- Tính hash của pattern và cửa sổ đầu: Θ(m).
- Duyệt tối đa n−m+1 cửa sổ, cập nhật hash cửa sổ mới O(1) mỗi bước: O(n).
- Mỗi lần hai hash bằng nhau, equalsAt có thể so tối đa m ký tự: O(m) cho một ứng viên.

Nếu q là số cửa sổ có hash bằng pattern và thực sự được kiểm tra trước khi hàm trả kết quả, tổng thời gian có cận:

~~~text
O(n + m + q*m), trong đó 0 <= q <= n-m+1.
~~~

Ở nhiều dữ liệu thông thường khi hash phân tán tốt và ít ứng viên, chi phí gần O(n+m). Nhưng **trường hợp tệ nhất vẫn O(nm)** nếu có rất nhiều ứng viên hash bằng cần so sánh dài rồi thất bại, chẳng hạn khi một đối thủ chủ động tạo dữ liệu va chạm. Không được ghi “Rabin–Karp có bảo đảm O(n) cho mọi dữ liệu” chỉ vì phép cập nhật hash là O(1).

Bộ nhớ phụ của chương trình là **O(1)** ngoài hai chuỗi đầu vào: vài biến số và không tạo mảng hash tiền tố hay bản sao cửa sổ. Nếu lựa chọn tiền xử lý prefix hashes để hỗ trợ rất nhiều truy vấn đoạn, bộ nhớ có thể tăng O(n), tùy cấu trúc.

### Xác suất va chạm không phải bảo đảm

Một mô hình hash ngẫu nhiên đều trên M giá trị thường cho xác suất va chạm của **một cặp cố định** khoảng 1/M. Nhưng chương trình sử dụng hash đa thức xác định với cơ số và mô-đun cố định; đầu vào thực tế hoặc dữ liệu do đối thủ chọn **không nhất thiết tuân theo mô hình ngẫu nhiên đều**. Vì vậy không suy ra được cận thời gian kỳ vọng từ 1/M nếu chưa nêu giả thiết phân phối hoặc cách lấy tham số ngẫu nhiên.

Nếu xét khoảng t dấu vân tay trong mô hình độc lập lý tưởng, xác suất có ít nhất một va chạm có thể tăng đáng kể khi t lớn (hiệu ứng sinh nhật), chứ không chỉ phụ thuộc vào xác suất của một cặp. Chọn hai mô-đun hoặc thêm bước so dữ liệu là các biện pháp cho những mục tiêu khác nhau: giảm số ứng viên so với **đảm bảo tính đúng**.

## 11. Ứng dụng trong tiền xử lý, tìm kiếm và khử trùng lặp

### 11.1. Tìm chuỗi con trong văn bản

Rabin–Karp tiền xử lý hash mẫu và duy trì hash của cửa sổ văn bản. Đây là ví dụ điển hình vì **mỗi cửa sổ kế tiếp gần giống cửa sổ trước**, nên rolling hash tiết kiệm công sức tính lại. Nếu kết quả phải đúng 100%, xác minh vẫn bắt buộc cho từng hash-equal candidate.

### 11.2. Lập chỉ mục các đoạn nội dung

Có thể chia tài liệu thành đoạn/chunk, tính fingerprint để **gom các đoạn đáng so sánh**, sau đó đối chiếu nội dung thật. Hash giúp giảm số cặp cần kiểm tra; nó không tự bảo đảm mọi chunk trong cùng bucket là cùng dữ liệu.

Nếu chunk được lấy theo ranh giới khác nhau, hai nguồn giống phần lớn nội dung nhưng lệch một byte có thể bị chia chunk khác hẳn. Đây là một vấn đề về **cách phân đoạn dữ liệu**, tách biệt với va chạm hash.

### 11.3. Truy vấn nhiều đoạn bằng prefix hash

Với cùng cơ số B và modulo P, có thể tiền xử lý:

~~~text
prefix[0] = 0
prefix[i+1] = (prefix[i] * B + code(s[i])) mod P
power[i]  = B^i mod P

H(s[l..r)) =
    (prefix[r] - prefix[l] * power[r-l]) mod P
~~~

Khi đã có prefix và power, có thể lấy fingerprint của một đoạn bất kỳ trong O(1) phép toán số, còn xây mảng tiền xử lý O(n) thời gian và **O(n) bộ nhớ**. Nếu cần kết luận hai đoạn bằng nhau tuyệt đối, bước đối chiếu nội dung vẫn cần thiết hoặc phải dùng cấu trúc dữ liệu có bảo đảm khác.

### 11.4. Dò bản sao tệp

Kích thước khác nhau ⇒ chắc chắn nội dung byte khác nhau. Kích thước giống và hash khác ⇒ chắc chắn byte khác nếu hash được tính trên đúng toàn bộ nội dung theo cùng quy tắc. Kích thước và hash giống ⇒ **ứng viên trùng**, cần so byte nếu quyết định đòi hỏi chính xác, ví dụ trước khi xóa bản sao duy nhất hoặc hợp nhất dữ liệu quan trọng.

Trước khi lưu fingerprint lâu dài, nên xác định phiên bản thuật toán và cách mã hóa; thay đổi cách băm hoặc chuẩn hóa mà không gắn phiên bản có thể làm việc so sánh sau này không nhất quán.

## 12. Dữ liệu văn bản, Unicode và cách xác định “bằng nhau”

Java String.length() và charAt(i) làm việc theo **đơn vị mã UTF-16**, không phải luôn theo “ký tự” người đọc cảm nhận. Một emoji ngoài Basic Multilingual Plane thường chiếm hai char. Thuật toán ở mục 8 tìm theo đơn vị mã UTF-16, tương tự quy ước chỉ số của String.indexOf(String).

Các lựa chọn khác nhau dẫn đến fingerprint khác nhau:

- **Chuỗi UTF-16**: cùng một dãy char thì cùng fingerprint, bao gồm cả thứ tự các surrogate code units.
- **Byte UTF-8**: cần mã hóa cả hai chuỗi bằng cùng charset (ví dụ StandardCharsets.UTF_8) rồi băm đúng byte. Chỉ số kết quả nếu tìm trên byte không còn là chỉ số char.
- **Unicode normalization**: chuỗi có “é” dạng một code point và dạng “e” cộng dấu kết hợp có thể hiển thị tương tự nhưng không bằng nhau theo UTF-16. Nếu coi là bằng về ngữ nghĩa chuẩn hóa, phải dùng cùng cách chuẩn hóa, chẳng hạn NFC, **trước cả băm và xác minh**.
- **Phân biệt hoa/thường, khoảng trắng, dấu câu**: muốn bỏ qua hay giữ phải đưa vào hợp đồng. Không được thay đổi quy tắc ở riêng một phía.
- **Bản ghi nhiều trường**: xác định serialization rõ ràng (độ dài, thứ tự trường, encoding), nếu không dữ liệu khác nhau có thể nối thành cùng chuỗi byte ngay **trước khi băm**; ví dụ các cặp ("ab","c") và ("a","bc") đều có chuỗi nối trực tiếp là "abc".

Cần phân biệt **va chạm do hàm băm** (hai byte sequence khác nhau cho cùng digest) với **nhập nhằng do mã hóa/serialization** (hai đối tượng khác nhau được mã hóa thành cùng byte sequence). Bước so sánh nội dung gốc sau băm phải dùng định nghĩa bằng nhau mà ứng dụng thực sự mong muốn.

## 13. Hash không mật mã, hash mật mã và xác thực

Fingerprint dùng cho sàng lọc thuật toán (như rolling hash modulo nguyên tố nhỏ) **không phải công cụ chứng thực an ninh**. Có ít nhất ba mục tiêu:

| Mục tiêu | Công cụ phù hợp hơn | Điều không nên suy luận |
| --- | --- | --- |
| Tìm nhanh vị trí chuỗi con | Rolling hash + so ký tự | Hash bằng chứng minh hai đoạn bằng |
| Kiểm tra lỗi ngẫu nhiên khi truyền tải | Checksum/CRC hoặc digest theo yêu cầu | CRC bảo vệ trước kẻ tấn công chủ động |
| Phát hiện thay đổi có đối thủ | Hash mật mã kết hợp nguồn digest tin cậy; HMAC hoặc chữ ký số khi cần xác thực | Chỉ công bố SHA-256 bên cạnh dữ liệu là bằng chứng dữ liệu do bên đáng tin tạo |

**SHA-256** được thiết kế để chống va chạm và các dạng tấn công khác mạnh hơn rolling hash, nhưng không tạo định lý “hai thông điệp có SHA-256 giống nhau thì chắc chắn bằng nhau”. Với nhu cầu bảo đảm tuyệt đối và dữ liệu gốc khả dụng, so byte vẫn là kiểm tra quyết định.

Nếu đối thủ có thể sửa cả dữ liệu lẫn digest được lưu bên cạnh, tự kiểm tra SHA-256 của dữ liệu với digest do cùng đối thủ cung cấp **không chứng minh tính xác thực**. Khi có khóa bí mật chia sẻ phù hợp, HMAC giúp xác thực tính toàn vẹn và nguồn tạo đối với các bên có khóa; chữ ký số giải quyết tình huống xác thực bằng khóa công khai theo mô hình tin cậy của ứng dụng.

Đây là hai bài toán khác nhau: **so trùng chính xác** và **bảo mật/xác thực**. Không nên biến một hàm băm nhanh cho tìm chuỗi thành cơ chế an ninh.

## 14. Bộ kiểm thử và cách tự xác minh thuật toán

### 14.1. Các tình huống cố định

| text | pattern | Kết quả | Ý nghĩa |
| --- | --- | ---: | --- |
| "zzabacaba" | "aba" | 2 | Lấy lần xuất hiện đầu tiên |
| "zzabacaba" | "xyz" | −1 | Không có mẫu |
| "abc" | "" | 0 | Mẫu rỗng |
| "" | "" | 0 | Cả hai rỗng |
| "" | "a" | −1 | Văn bản rỗng, mẫu không rỗng |
| "ab" | "abc" | −1 | Mẫu dài hơn văn bản |
| "aaaaa" | "aaa" | 0 | Các lần xuất hiện chồng nhau; trả đầu tiên |
| "A😀B😀" | "😀B" | 1 | Chỉ số theo UTF-16 |
| "abc" | "ABC" | −1 | Phân biệt chữ hoa/chữ thường |
| null | "a" | NullPointerException | Không chấp nhận null |

Ngoài các ví dụ cố định, nên so sánh phương thức indexOf tự viết với **String.indexOf(pattern)** trên nhiều cặp chuỗi ngắn sinh tự động, có ký tự trùng, ký tự không ASCII, emoji, mẫu rỗng và mẫu không tồn tại. Hai phương thức cùng hợp đồng trả vị trí bắt đầu theo UTF-16 nên có thể đối chiếu trực tiếp.

Khi viết property test, đừng chỉ kiểm tra “kết quả nằm trong khoảng”: cần xác nhận rằng nếu kết quả i≥0 thì đoạn từ i dài m bằng đúng pattern, **không có vị trí trước i khớp**, và nếu trả −1 thì không có khớp nào.

### 14.2. Kiểm thử va chạm có chủ đích

Hàm toyHash trong chương trình tạo cùng giá trị 67 cho "aZ" và "b;", dù hai chuỗi khác. Kết quả này kiểm tra **không được bỏ qua phép so dữ liệu**.

Với một hash dùng trong thuật toán thực tế, có thể tạo bộ test nhỏ với MOD đồ chơi để dễ gây va chạm và kiểm tra rằng ứng viên va chạm **không được công nhận** khi equalsAt thất bại. Lưu ý bản chính dùng MOD lớn và vẫn so ký tự: thay MOD trong một bản test phải bảo đảm tính toán không tràn và phép rolling đồng nhất trên cả pattern lẫn các cửa sổ.

### 14.3. Kiểm thử độ phức tạp, không bịa số đo

Có thể đếm riêng số lần trượt cửa sổ, số lần hash bằng và số ký tự thực sự được đối chiếu. Đo thời gian JVM cần khởi động/warm-up, lặp lại nhiều lần và dùng cùng dữ liệu cho các thuật toán so sánh. Không suy ra “luôn nhanh hơn String.indexOf” từ việc có rolling hash: thư viện Java có thể có triển khai tìm chuỗi tối ưu và độ dài mẫu/phân bố dữ liệu ảnh hưởng hiệu quả thực tế.

Tách độ phức tạp của **tiền xử lý** và **một truy vấn**, nhất là khi dùng prefix hashes cho nhiều truy vấn. Bộ nhớ bảng prefix O(n) không được nhầm với bộ nhớ O(1) của bản rolling chỉ giữ một cửa sổ.

## 15. Những sai lầm thường gặp

1. **So hash rồi trả “giống nhau” ngay.** Một va chạm có thể biến kết luận thành sai. Với yêu cầu chính xác, phải đối chiếu nội dung.
2. **Cho rằng hash mật mã không thể va chạm.** Hash đầu ra hữu hạn luôn có va chạm trên miền đầu vào đủ lớn, dù độ khó tìm có thể rất cao.
3. **Dùng HashMap hashCode như phép định danh duy nhất.** equals quyết định bằng nhau theo hợp đồng khóa; hashCode chỉ hỗ trợ chọn bucket.
4. **Trộn nhiều cách mã hóa.** UTF-8 bytes và UTF-16 code units tạo fingerprint khác nhau, ngay cả khi hiển thị cùng văn bản.
5. **Nhầm chiều suy luận.** H(A)≠H(B) chứng minh A≠B nếu H được áp dụng đúng trên cùng biểu diễn; H(A)=H(B) không chứng minh A=B.
6. **Quên cập nhật hash khi trượt.** Phải bỏ đúng ký tự đầu với trọng số B^(m−1), nhân B rồi thêm ký tự mới.
7. **Để số dư âm sau phép trừ.** Chuẩn hóa modulo đúng trước khi nhân/cộng ký tự vào.
8. **Dùng kiểu int cho tích lớn.** Phép nhân có thể tràn trước khi lấy %; dùng long và kiểm tra giới hạn nhân với MOD/BASE đã chọn.
9. **Không xử lý mẫu rỗng hoặc mẫu dài hơn văn bản.** Dễ dẫn đến sai ranh giới hoặc lặp không cần thiết.
10. **Tuyên bố worst-case O(n+m) cho Rabin–Karp có xác minh.** Nhiều ứng viên hash bằng và khác nội dung có thể gây O(nm).
11. **Dùng hai hash và bỏ bước xác minh vì “gần như chắc chắn”.** Giảm rủi ro không tương đương chứng minh đúng tuyệt đối.
12. **Gán fingerprint của dữ liệu đang thay đổi cho kết quả bất biến.** Nếu nội dung bị sửa sau khi tính, fingerprint cũ không đại diện cho phiên bản mới.
13. **Đồng nhất trùng nội dung với trùng ngữ nghĩa.** Dữ liệu hiển thị giống nhau, khác chuẩn hóa Unicode hay trường dữ liệu, cần quy tắc so sánh cụ thể.
14. **Sử dụng rolling hash cho xác thực chống giả mạo.** Đây là công cụ thuật toán, không phải MAC hay chữ ký số.
15. **Không đếm chi phí xác minh.** Băm nhanh nhưng nhiều false positives có thể làm tổng thời gian tăng mạnh.

## 16. Checklist áp dụng

- [ ] Đã định nghĩa chính xác đơn vị dữ liệu cần so: byte, UTF-16, code point hay bản ghi được chuẩn hóa?
- [ ] Hàm băm được áp dụng nhất quán cho cả mẫu và ứng viên?
- [ ] Đã hiểu va chạm tồn tại dù dấu vân tay trông “duy nhất”?
- [ ] Khi hash bằng, đã có bước **xác minh nội dung thật** nếu đòi kết quả chắc chắn?
- [ ] Với rolling hash, đã kiểm tra công thức bỏ ký tự đầu, dịch trọng số và thêm ký tự cuối?
- [ ] Kiểu số và phép modulo có tránh tràn/giá trị âm sai không?
- [ ] Ranh giới cửa sổ, mẫu rỗng, null và Unicode được xử lý theo hợp đồng?
- [ ] Đã phân biệt cận thời gian rolling O(n+m) và chi phí xác minh ứng viên O(qm)?
- [ ] Đã cộng đủ chi phí bảng prefix nếu dùng tiền xử lý nhiều truy vấn?
- [ ] Nếu có đối thủ, đã dùng cơ chế mật mã phù hợp thay vì hash không mật mã?
- [ ] Đã kiểm thử va chạm đồ chơi và so kết quả tìm kiếm với một oracle chính xác?

**Kết luận:** dấu vân tay dữ liệu là công cụ **tiền xử lý và lọc nhanh**. Tính chất đáng tin cậy là “nội dung bằng nhau ⇒ hash bằng nhau”; chiều ngược lại không đúng do **va chạm**. Vì vậy, trong những thuật toán như Rabin–Karp hoặc hệ thống khử trùng lặp đòi đáp án chính xác, **hash chọn ứng viên, còn phép so nội dung xác nhận kết quả**.

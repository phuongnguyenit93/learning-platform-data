# Xử lý số âm, độ dài khóa và thứ tự ký tự trong sắp xếp phân phối

## 1. Vì sao ba chi tiết này quyết định tính đúng?

**Sắp xếp phân phối** (distribution-based sorting) khai thác thông tin về miền giá trị hoặc cấu trúc khóa thay vì chỉ so sánh từng cặp phần tử. Các họ thuật toán tiêu biểu gồm **counting sort** (đếm), **radix sort** (theo chữ số/vị trí của khóa) và **bucket sort** (phân vào các nhóm). Khi có đủ giả thiết, chúng có thể đạt thời gian tuyến tính hoặc gần tuyến tính theo kích thước dữ liệu và miền khóa.

Tuy nhiên, lời giải đúng với các số nguyên không âm nhỏ hoặc chuỗi có độ dài cố định có thể sai khi gặp:

- **Số âm:** lấy giá trị làm chỉ số mảng đếm gây chỉ số âm; lấy chữ số bằng phép chia/phần dư trên số âm không cho dãy chữ số không âm như mong đợi; dấu của số nguyên có thể khiến radix sort đưa số âm ra sau số dương.
- **Khóa có độ dài khác nhau:** với hai chuỗi "a" và "aa", so sánh từ điển phải đặt "a" trước "aa". Nếu tự đệm bằng ký tự không phù hợp hoặc bỏ qua vị trí thiếu, kết quả có thể sai.
- **Thứ tự ký tự:** thứ tự theo mã đơn vị UTF-16, theo Unicode code point và theo quy tắc ngôn ngữ tự nhiên (collation) **không phải cùng một thứ tự**. "Z" đứng trước "a" theo thứ tự mã thông thường, nhưng thứ tự thân thiện với người đọc có thể khác.

Bài học không đặt mục tiêu “chữa” mọi biến thể bằng một mẹo duy nhất. Mục tiêu là **đặc tả rõ khóa, quan hệ thứ tự, phép ánh xạ sang bucket/digit và điều kiện ổn định** trước khi áp dụng thuật toán phân phối.

Một sắp xếp đúng phải thỏa hai hậu điều kiện: (1) dãy đầu ra có cùng đa tập bản ghi/phần tử như đầu vào; (2) các phần tử được xếp theo **đúng quan hệ thứ tự đã chọn**. Nếu yêu cầu **ổn định** (stable), các bản ghi có khóa bằng nhau còn phải giữ nguyên thứ tự xuất hiện tương đối.

## 2. Chọn thuật toán dựa trên miền khóa

| Thuật toán | Thông tin cần có | Thời gian thường dùng | Bộ nhớ phụ điển hình | Điểm dễ sai |
| --- | --- | --- | --- | --- |
| Counting sort | Khóa nguyên thuộc miền nhỏ gồm R giá trị | O(n + R) | O(n + R) nếu xuất ổn định | Khóa âm, miền rộng, lệch chỉ số |
| LSD radix sort | Có thể tách khóa thành d chữ số trên cơ số b; từng lượt stable | O(d(n + b)) | O(n + b) | Thứ tự chữ số, ổn định, dấu, độ dài khóa |
| MSD radix sort | Có thể phân nhóm theo ký tự/chữ số từ trái qua phải | Phụ thuộc chiều dài khóa, kích thước bucket và cách cài | Phụ thuộc cài đặt | Khóa kết thúc sớm, nhánh rỗng, bộ nhớ/đệ quy |
| Bucket sort | Có phép ánh xạ khóa vào nhóm bảo toàn thứ tự | Kỳ vọng có thể O(n + k) với phân bố phù hợp và k bucket | O(n + k) | Ánh xạ số âm, biên bucket, phân bố lệch |
| Sắp xếp so sánh | Có comparator xác định một thứ tự nhất quán | Thường O(n log n) | Phụ thuộc thuật toán | Comparator sai, không ổn định nếu yêu cầu |

Ký hiệu n là số phần tử, R là độ rộng miền khóa, d là số lượt xử lý chữ số, b là cơ số (số giá trị digit), k là số bucket. Không thể tuyên bố counting sort O(n) nếu R rất lớn; tương tự, radix sort không mặc nhiên O(n) khi d tăng theo độ dài biểu diễn khóa.

**Câu hỏi đầu tiên trước khi triển khai:** ta đang sắp xếp giá trị số có dấu, chuỗi số, chuỗi ký tự, hay bản ghi có nhiều trường? Các kiểu này có thể cần ánh xạ khóa khác nhau dù bề ngoài cùng được viết dưới dạng ký tự.

## 3. Counting sort với số âm: dịch miền về chỉ số không âm

Counting sort dựa trên tần suất của từng khóa. Đối với số nguyên có thể âm, ta không truy cập trực tiếp count[x]. Thay vào đó, tìm **min** và **max** của dãy, rồi ánh xạ:

~~~text
index(x) = x - min
range    = max - min + 1
~~~

Vì min ≤ x ≤ max nên index(x) nằm trong [0,range-1], luôn không âm. Sau khi đếm, vị trí d trong count đại diện cho khóa d + min.

Ví dụ với a = [-3, 2, -1, -3, 0]:

~~~text
min=-3, max=2, range=6

gia tri:    -3  -2  -1   0   1   2
chi so:      0   1   2   3   4   5
tan suat:    2   0   1   1   0   1

ket qua: [-3, -3, -1, 0, 2]
~~~

**Lưu ý tràn số:** nếu min = Integer.MIN_VALUE và max = Integer.MAX_VALUE thì phép max-min+1 tính bằng int có thể tràn và kết quả thật là 4.294.967.296 giá trị, quá lớn để cấp phát thông thường. Cần ép sang long **trước khi trừ**:

~~~java
long range = (long) max - (long) min + 1L;
long offset = (long) value - (long) min;
~~~

Chỉ chuyển range/offset về int sau khi đã xác minh miền nhỏ đủ, không âm và hợp lệ. Một thuật toán đúng về mặt toán học nhưng cố cấp phát mảng đếm hàng tỉ phần tử vẫn không phải lựa chọn có thể triển khai.

### Counting sort ổn định

Nếu chỉ xử lý int, xuất mỗi giá trị theo số lần đếm là đủ để sắp xếp giá trị. Nhưng nếu phần tử là bản ghi (score, id), muốn giữ nguyên thứ tự các id có cùng score thì cần **counting sort ổn định**:

1. Đếm tần suất từng chỉ số khóa.
2. Tính **tổng tiền tố bao gồm**: count[d] sau bước này bằng số phần tử có khóa ≤ d.
3. Duyệt dữ liệu đầu vào **từ phải sang trái**; với bản ghi có khóa d, đặt vào vị trí --count[d] của mảng kết quả.
4. Không thay đổi nội dung khóa trong quá trình phân phối.

Duyệt ngược là yếu tố giữ ổn định khi dùng tổng tiền tố cuối đoạn: bản ghi xuất hiện sau được điền vào vị trí trống bên phải trước, bản ghi xuất hiện trước được điền vào vị trí bên trái. Nếu dùng tổng tiền tố **loại trừ** làm chỉ số bắt đầu bucket, có thể duyệt từ trái sang phải và tăng con trỏ sau khi đặt; cả hai biến thể đều ổn định khi triển khai đúng.

**Độ phức tạp:** thời gian O(n+R), bộ nhớ O(n+R) nếu cần mảng kết quả ổn định. Với chỉ số khóa âm, cộng dồn bằng int an toàn khi n là độ dài mảng Java hợp lệ, nhưng phép tính độ rộng miền khóa vẫn phải dùng long.

### Khi nào không nên dùng counting sort?

Nếu n=100 nhưng khóa nằm từ -2.000.000.000 đến 2.000.000.000, R cực lớn so với n; offset giúp khắc phục chỉ số âm **nhưng không khắc phục chi phí bộ nhớ**. Hãy cân nhắc radix sort với số lượt cố định, sắp xếp so sánh, hoặc nén tọa độ nếu phù hợp với các thao tác sau đó.

## 4. Radix sort số nguyên có dấu: biến đổi khóa bảo toàn thứ tự

Radix sort (cơ số) sắp xếp khóa thông qua nhiều lượt phân phối theo chữ số. Với **LSD radix sort** (least significant digit first), ta đi từ chữ số **ít quan trọng nhất** tới **quan trọng nhất**. Mỗi lượt phải dùng phép sắp xếp **ổn định**; nếu không, các quan hệ thứ tự đã hình thành ở các chữ số kém quan trọng hơn sẽ bị phá.

Với số nguyên **không âm** có độ rộng cố định, có thể dùng các digit 0..9 hoặc các nhóm 8 bit 0..255. Tuy nhiên, với Java int có dấu và biểu diễn bù hai, nếu sắp theo các byte thô như số không dấu thì các số âm có bit dấu 1 sẽ bị đặt **sau** số không âm. Điều đó ngược với thứ tự tăng dần của int có dấu.

### Biến đổi dấu bằng XOR bit cao nhất

Một phép biến đổi tiện lợi cho **int 32 bit của Java** là:

~~~java
int key = value ^ Integer.MIN_VALUE;
~~~

Integer.MIN_VALUE có bit dấu cao nhất bằng 1 và các bit khác bằng 0. XOR lật đúng bit cao nhất, ánh xạ thứ tự số nguyên **có dấu** thành thứ tự **không dấu** của 32 bit:

| Giá trị int | Bit sau XOR, viết hex | Vị trí theo thứ tự unsigned |
| --- | --- | --- |
| Integer.MIN_VALUE | 0x00000000 | Nhỏ nhất |
| -1 | 0x7FFFFFFF | Cuối nhóm âm |
| 0 | 0x80000000 | Đầu nhóm không âm |
| Integer.MAX_VALUE | 0xFFFFFFFF | Lớn nhất |

Ta **không** thay đổi giá trị đầu ra; phép XOR chỉ được dùng khi lấy digit để phân phối. Từng digit ở lượt shift = 0, 8, 16, 24:

~~~java
int digit = ((value ^ Integer.MIN_VALUE) >>> shift) & 0xFF;
~~~

Toán tử >>> là **dịch phải không giữ dấu** trong Java, còn & 0xFF lấy đúng một byte có giá trị 0..255. Sau bốn lượt stable, các giá trị int được sắp theo thứ tự tăng dần có dấu, kể cả Integer.MIN_VALUE, số âm lặp và Integer.MAX_VALUE.

### Vì sao bốn lượt stable là đủ?

Sau lượt xử lý byte thứ 0, dãy được sắp theo byte thấp nhất. Sau lượt byte thứ 1 ổn định, dãy được sắp theo **cặp** byte thấp nhất; tính ổn định giữ thứ tự byte 0 khi byte 1 bằng nhau. Lặp đến byte thứ 3, dãy được sắp theo toàn bộ khóa biến đổi 32 bit ở thứ tự unsigned; phép XOR giúp thứ tự đó trùng với thứ tự signed int ban đầu. Mỗi lượt dùng counting distribution trên 256 bucket.

Với int 32 bit, tổng thời gian O(4(n+256)) = O(n+256), bộ nhớ phụ O(n+256). Đây là kết quả theo **độ rộng khóa cố định**. Đối với khóa dài tùy ý, số lượt d không còn là hằng số, phải tính thành O(d(n+b)).

### Cách khác: phân phối riêng âm và không âm

Có thể tách giá trị âm và không âm, sắp từng nhóm rồi ghép **âm trước, không âm sau**. Nhưng cần xử lý thứ tự đúng trong nhóm âm: nếu so theo **độ lớn tuyệt đối**, số có độ lớn lớn hơn phải đứng trước (ví dụ -12 trước -3). Trong Java, Math.abs(Integer.MIN_VALUE) vẫn cho giá trị âm do không biểu diễn được +2.147.483.648 bằng int. Muốn chuyển sang độ lớn tuyệt đối phải tính bằng long trước hoặc dùng phép biến đổi bit an toàn như trên.

Cách dùng XOR phù hợp khi đang sắp int bit rộng cố định; không áp dụng nguyên xi phép XOR Integer.MIN_VALUE cho long, BigInteger, số thực hoặc chuỗi số thập phân. Mỗi kiểu cần thiết kế khóa tương ứng.

## 5. Khóa số được biểu diễn bằng chuỗi: thứ tự số khác thứ tự từ điển

Cần phân biệt **chuỗi ký tự** với **giá trị số**:

- So sánh từ điển theo ký tự: "10" đứng trước "2" vì ký tự đầu '1' nhỏ hơn '2'.
- So sánh giá trị số: 2 đứng trước 10.
- "02" và "2" có thể biểu diễn **cùng giá trị số** nhưng không phải hai chuỗi bằng nhau; nếu sắp bản ghi cần quy tắc xử lý số 0 đứng đầu.
- "-12" và "-3": theo ký tự, sau dấu '-' ký tự '1' nhỏ hơn '3' nên "-12" đứng trước "-3"; điều này trùng thứ tự số ở ví dụ nhưng không thể suy ra nguyên tắc chung cho mọi chữ số bằng phép so sánh ký tự thông thường (chẳng hạn "-2" so với "-10" sẽ cho kết quả sai về mặt số học).

Nếu các chuỗi đều là **số thập phân không âm dạng chuẩn** (không có số 0 thừa ở đầu, ngoại trừ chuỗi "0"), so sánh giá trị số tương đương với:

1. Chuỗi có ít chữ số hơn đứng trước.
2. Khi cùng độ dài, so sánh từ điển theo từng chữ số 0..9.

Với **số âm dạng chuỗi**, trước hết đặt âm trước không âm; giữa hai số âm, so sánh độ lớn tuyệt đối **ngược chiều**, không cần chuyển sang int/long nếu số có thể dài tùy ý. Dữ liệu còn có thể chứa dấu '+', các dạng "-0"/"0", khoảng trắng hoặc số 0 thừa; phải quy định chuẩn hóa, giá trị bằng nhau và tính ổn định trước khi triển khai.

Đừng chỉ xóa ký tự '-' rồi radix sort mọi chuỗi như một số dương: điều này sẽ xếp -3 trước -12 nếu số 3 nhỏ hơn 12, ngược thứ tự số nguyên đúng.

## 6. Chuỗi độ dài khác nhau: ký hiệu kết thúc và thứ tự tiền tố

Thứ tự từ điển (lexicographic) trên **cùng một bảng chữ cái** được xác định như sau:

1. So sánh các ký tự/đơn vị khóa từ trái sang phải.
2. Ở vị trí khác nhau đầu tiên, chuỗi chứa ký tự nhỏ hơn đứng trước.
3. Nếu một chuỗi là tiền tố đúng của chuỗi kia, **chuỗi ngắn hơn đứng trước**.

Ví dụ:

~~~text
"" < "a" < "aa" < "ab" < "aba" < "b" < "bat"
~~~

Nếu thuật toán phân phối yêu cầu mọi khóa có độ dài L cố định, chuỗi ngắn hơn cần cách biểu diễn các vị trí không tồn tại. Đối với thứ tự từ điển thông thường, ta có thể chọn **ký hiệu kết thúc (EOS)** nhỏ hơn mọi ký tự hợp lệ. Khi đó:

~~~text
alphabet: EOS=0, 'a'=1, 'b'=2, ..., 'z'=26

"a"   -> ['a', EOS, EOS, ...]
"aa"  -> ['a', 'a', EOS, ...]
"ab"  -> ['a', 'b', EOS, ...]
""    -> [EOS, EOS, ...]
~~~

Sau khi xử lý từ trái sang phải ở mức ý nghĩa của khóa, EOS bảo đảm chuỗi tiền tố ngắn hơn đứng trước chuỗi dài hơn. Ta không bắt buộc phải nối ký tự EOS vào dữ liệu thật: chỉ cần hàm lấy digit trả 0 khi vị trí đang xét vượt quá chiều dài chuỗi.

**Điều kiện:** EOS phải đứng trước mọi ký tự hợp lệ trong thứ tự khóa. Nếu dùng ký tự 'z' hoặc khoảng trắng tùy tiện làm phần đệm, thứ tự có thể sai. Nếu cho phép cả ký tự U+0000 trong dữ liệu, không nên dùng chính U+0000 như ký hiệu kết thúc không phân biệt; hãy dùng digit tách biệt (ví dụ digit codepoint+1) khi có ngân sách bộ nhớ thích hợp.

### LSD radix sort cho chuỗi độ dài thay đổi

Với miền ký tự nhỏ (ví dụ a..z), có thể xử lý từ vị trí L-1 về 0, trong đó L là **độ dài lớn nhất**. Ở mỗi vị trí p, digit là:

~~~text
digit(s,p) = 0                   neu p >= length(s)
digit(s,p) = s[p] - 'a' + 1      neu 'a' <= s[p] <= 'z'
~~~

Mỗi lượt dùng counting sort **ổn định** theo digit hiện tại. Nhờ EOS nhỏ nhất, sau lượt p=0, thứ tự cuối cùng là thứ tự từ điển trên a..z, bao gồm chuỗi rỗng và chuỗi là tiền tố của nhau.

Nếu dùng bảng chữ cái kích thước b và L vị trí, cách LSD đơn giản tốn **O(L(n+b))** thời gian và O(n+b) bộ nhớ phụ, có thể tốn công đọc nhiều vị trí thiếu ở các chuỗi rất ngắn. Ưu điểm là cài đặt dễ kiểm chứng khi L và b nhỏ. Nhược điểm là cần kiểm tra đầu vào thuộc đúng alphabet, từng lượt phải stable và không nên cấp phát b rất lớn khi nhiều ký tự ít xuất hiện.

### MSD radix sort cho chuỗi

**MSD radix sort** phân phối theo ký tự quan trọng nhất trước, rồi chỉ sắp tiếp **các bucket có cùng tiền tố** ở ký tự kế tiếp. Khi gặp EOS, chuỗi đã kết thúc và không cần phân phối sâu nữa. MSD thường phù hợp cho khóa có tiền tố chung và độ dài biến thiên, nhưng cần cẩn thận với trường hợp kết thúc sớm, bucket kích thước 0/1, độ sâu đệ quy và các chuỗi dài.

**LSD so với MSD:** cả hai có thể cho cùng thứ tự từ điển khi thiết kế đúng. Không nên khẳng định chúng có cùng chi phí, vì LSD thường xử lý mọi chuỗi đến L vị trí, còn MSD xử lý theo từng nhóm tiền tố và việc triển khai có thể khác nhau.

## 7. “Thứ tự ký tự” thực sự có nghĩa gì?

Đây là chỗ thuật toán phân phối dễ bị nhầm nhất khi xử lý văn bản. Trước khi gán digit/bucket cho ký tự, phải chọn **một định nghĩa thứ tự**.

### 7.1 Mã ASCII hoặc bảng chữ cái được giới hạn

Với dữ liệu chắc chắn chỉ chứa ký tự ASCII thường 'a'..'z', có thể ánh xạ 'a'=1,...,'z'=26 (EOS=0). Khi đó thứ tự từ điển theo mã trùng với thứ tự chữ cái tiếng Anh viết thường. Đây là giới hạn của ví dụ Java bên dưới, **không phải giải pháp chung cho tiếng Việt hay Unicode**.

Khi có ký tự viết hoa, chữ số hoặc dấu câu, thứ tự theo mã có thể gây ngạc nhiên: trong Java, "Z".compareTo("a") < 0. Muốn không phân biệt hoa/thường, phải định nghĩa cách quy đổi và xử lý trường hợp hòa; dùng toLowerCase() mà không đặt Locale và không xét Unicode có thể không đáp ứng yêu cầu nghiệp vụ.

### 7.2 Java String.compareTo và đơn vị mã UTF-16

Java String lưu và so sánh theo **đơn vị mã UTF-16** (char), không phải mặc định theo thứ tự các Unicode code point. Với các ký tự ngoài Basic Multilingual Plane, một code point được biểu diễn bằng **cặp surrogate**. Vì vậy:

- String.length() đếm đơn vị mã UTF-16, không nhất thiết đếm số ký tự Unicode/code point hay số “chữ” người dùng nhìn thấy.
- String.charAt(i) trả về một **char**, có thể là một nửa cặp surrogate.
- String.codePoints() hoặc codePointAt(...) cho phép đi theo code point (với chỉ số UTF-16 phải sử dụng đúng).
- Thứ tự của String.compareTo có thể **khác** thứ tự theo code point: U+1F600 được mã hóa bắt đầu bằng high surrogate 0xD83D, vốn nhỏ hơn U+E000 khi so đơn vị UTF-16, mặc dù U+1F600 lớn hơn U+E000 theo giá trị code point.

Nếu đặc tả yêu cầu “sắp đúng như String.compareTo của Java”, radix sort cần xử lý các **đơn vị mã UTF-16 theo thứ tự của chúng**; nếu yêu cầu code point, phải trích xuất code point và thiết kế ánh xạ tương ứng. Đừng trộn cách lấy độ dài theo code point với charAt theo chỉ số UTF-16.

### 7.3 Tiếng Việt, dấu và quy tắc ngôn ngữ

Sắp xếp văn bản tự nhiên còn phức tạp hơn:

- Ký tự có dấu có thể có dạng Unicode **đã hợp thành** (ví dụ U+00E9) hoặc chữ cơ sở kết hợp với **dấu tổ hợp** (ví dụ U+0065 U+0301). Hai chuỗi hiển thị gần như giống nhau có thể gồm các dãy code point khác nhau.
- Phân biệt chữ hoa/chữ thường, dấu, các dấu thanh và quy tắc bảng chữ cái Việt Nam là yêu cầu **collation**, không phải một phép so sánh mã số đơn giản.
- Trong Java có thể dùng java.text.Normalizer để quy về dạng NFC/NFD khi yêu cầu, và java.text.Collator với Locale.forLanguageTag("vi-VN") để so sánh theo quy tắc ngôn ngữ. Cần kiểm thử theo locale/JDK và cấu hình độ nhạy dấu/hoa-thường phù hợp với yêu cầu.
- Những ký tự người dùng cảm nhận là một “chữ” có thể gồm nhiều code point (grapheme cluster). Sắp theo code point cũng không đồng nghĩa tự động sắp đúng theo tên/ngôn ngữ.

Nếu đề bài yêu cầu thứ tự tiếng Việt tự nhiên hoặc một quy tắc đặt tên phức tạp, **sắp xếp so sánh bằng Collator/Comparator** thường đơn giản và dễ bảo đảm đúng hơn một radix sort tùy biến. Muốn radix sort theo collation phải xây được khóa phân phối bảo toàn đúng quan hệ thứ tự (chẳng hạn khóa collation được xác định và kiểm thử), không được chỉ gán cho từng char một thứ tự tùy đoán.

## 8. Bucket sort với giá trị âm và biên khoảng

Bucket sort chia miền khóa thành nhiều khoảng có thứ tự; sắp từng bucket bằng một thuật toán phù hợp rồi nối các bucket theo thứ tự tăng dần. Điều quan trọng không phải chỉ “chia đều” mà là **mọi khóa trong bucket trước phải ≤ mọi khóa trong bucket sau**.

Với khóa nguyên và bucket độ rộng w > 0, một cách ánh xạ là:

~~~text
bucket(x) = floor((x - min) / w)
~~~

Ở đây min là cận dưới của miền chứa mọi giá trị, và phép trừ/chia phải tránh tràn. Với số âm, phân biệt **floor** với phép chia nguyên của Java: Java chia số nguyên theo hướng về 0. Ví dụ -1/10 bằng 0 trong Java, còn Math.floorDiv(-1,10) bằng -1. Nếu cách phân bucket dùng miền có cả phần âm và phần dương, sai khác này có thể chuyển khóa vào bucket sai. Hãy xây công thức trên kiểu đủ rộng, dùng Math.floorDiv khi cần làm tròn xuống, hoặc dịch bằng min để hiệu không âm rồi chia có kiểm soát.

Với số thực, công thức phổ biến là bucket = floor(k × (x-min)/(max-min)) cho min≤x≤max, sau đó **chặn chỉ số cuối** khi x=max nếu công thức tạo chỉ số k. Trường hợp max=min phải được xử lý riêng để tránh chia cho 0. NaN và vô cực không thuộc thứ tự số thực hữu hạn thông thường; phải xác định chính sách trước khi lập bucket.

**Độ phức tạp:** nếu dữ liệu được phân bố gần đều và mỗi bucket có ít phần tử, bucket sort có thể đạt thời gian kỳ vọng gần O(n+k) với phương pháp sắp trong bucket phù hợp. Nếu mọi giá trị dồn vào một bucket và sắp bucket đó bằng insertion sort, trường hợp xấu nhất có thể O(n²). Đừng suy ra O(n) mà không nói rõ giả thiết phân bố và chi phí sắp bên trong bucket.

**Ổn định:** muốn toàn bộ bucket sort ổn định, cách phân phối phải giữ thứ tự trong mỗi bucket và cách sắp từng bucket phải ổn định khi các khóa bằng nhau. Thuật toán bucket sort không mặc nhiên ổn định chỉ vì được gọi là “distribution sort”.

## 9. Java 17+: ba ví dụ tự chạy và kiểm tra được

Chương trình sau thể hiện ba tình huống riêng:

1. **Counting sort có số âm** bằng offset từ min, dùng long khi tính miền khóa và từ chối miền quá lớn cho ví dụ.
2. **LSD radix sort cho int có dấu**, bốn lượt trên 256 bucket, dùng XOR bit dấu.
3. **LSD radix sort chuỗi độ dài khác nhau**, chỉ chấp nhận chữ thường ASCII 'a'..'z' và dùng EOS=0. Nó không cố giả làm bộ sắp xếp tiếng Việt hoặc Unicode tổng quát.

Mỗi lượt phân phối là **ổn định**: counting sort đi ngược với tổng tiền tố bao gồm, còn hai phiên bản radix dùng tổng tiền tố loại trừ rồi đi xuôi theo nguồn.

Lưu thành tệp **DistributionKeysDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class DistributionKeysDemo {
    private static final long MAX_COUNT_RANGE = 1_000_000L;

    static int[] countingSortSigned(int[] input) {
        Objects.requireNonNull(input, "input");
        if (input.length == 0) {
            return new int[0];
        }

        int min = input[0];
        int max = input[0];
        for (int x : input) {
            min = Math.min(min, x);
            max = Math.max(max, x);
        }

        long range = (long) max - (long) min + 1L;
        if (range > MAX_COUNT_RANGE) {
            throw new IllegalArgumentException("range too large for counting sort");
        }

        int[] count = new int[(int) range];
        for (int x : input) {
            int digit = (int) ((long) x - (long) min);
            count[digit]++;
        }

        // Inclusive prefix sums: count[d] la cuoi bucket d.
        for (int d = 1; d < count.length; d++) {
            count[d] += count[d - 1];
        }

        int[] result = new int[input.length];
        for (int i = input.length - 1; i >= 0; i--) {
            int digit = (int) ((long) input[i] - (long) min);
            result[--count[digit]] = input[i];
        }
        return result;
    }

    // Bon luot, moi luot xet 8 bit cua khoa da lat bit dau.
    static int[] radixSortSigned(int[] input) {
        Objects.requireNonNull(input, "input");
        int[] source = input.clone();
        int[] target = new int[source.length];

        for (int shift = 0; shift < 32; shift += 8) {
            int[] start = new int[256];

            for (int x : source) {
                int digit = ((x ^ Integer.MIN_VALUE) >>> shift) & 0xFF;
                start[digit]++;
            }

            // Exclusive prefix sums: start[d] la vi tri dau bucket.
            int offset = 0;
            for (int d = 0; d < start.length; d++) {
                int amount = start[d];
                start[d] = offset;
                offset += amount;
            }

            // Duyet xuoi: cac gia tri co cung digit giu thu tu cu.
            for (int x : source) {
                int digit = ((x ^ Integer.MIN_VALUE) >>> shift) & 0xFF;
                target[start[digit]++] = x;
            }

            int[] temporary = source;
            source = target;
            target = temporary;
        }
        return source;
    }

    // Chi ho tro cac chuoi chu thuong ASCII a..z, ke ca chuoi rong.
    private static int digitAt(String s, int position) {
        return position < s.length() ? s.charAt(position) - 'a' + 1 : 0;
    }

    static String[] lsdLowercase(String[] input) {
        Objects.requireNonNull(input, "input");
        int maxLength = 0;
        for (String word : input) {
            Objects.requireNonNull(word, "word");
            maxLength = Math.max(maxLength, word.length());
            for (int i = 0; i < word.length(); i++) {
                char c = word.charAt(i);
                if (c < 'a' || c > 'z') {
                    throw new IllegalArgumentException("only a-z supported");
                }
            }
        }

        String[] source = input.clone();
        String[] target = new String[source.length];

        for (int position = maxLength - 1; position >= 0; position--) {
            int[] start = new int[27]; // 0=EOS, 1..26='a'..'z'

            for (String word : source) {
                start[digitAt(word, position)]++;
            }

            int offset = 0;
            for (int d = 0; d < start.length; d++) {
                int amount = start[d];
                start[d] = offset;
                offset += amount;
            }

            for (String word : source) {
                target[start[digitAt(word, position)]++] = word;
            }

            String[] temporary = source;
            source = target;
            target = temporary;
        }
        return source;
    }

    public static void main(String[] args) {
        int[] signed = {-3, 2, -1, -3, 0};
        System.out.println("counting = " +
                Arrays.toString(countingSortSigned(signed)));
        System.out.println("original = " + Arrays.toString(signed));

        int[] wide = {
                Integer.MAX_VALUE, -1, 0, Integer.MIN_VALUE, 7, -7
        };
        System.out.println("radix = " +
                Arrays.toString(radixSortSigned(wide)));

        String[] words = {"bat", "a", "ab", "", "aba", "aa", "a", "b"};
        String[] sortedWords = lsdLowercase(words);
        System.out.println("strings = " + Arrays.toString(sortedWords));
        System.out.println("first is empty = " + sortedWords[0].isEmpty());
        System.out.println("UTF16 Z before a = " + ("Z".compareTo("a") < 0));

        try {
            lsdLowercase(new String[]{"a", "é"});
        } catch (IllegalArgumentException ex) {
            System.out.println("unsupported = " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac DistributionKeysDemo.java
java DistributionKeysDemo
~~~

**Stdout chính xác** (trong dòng "strings", khoảng trống đầu biểu thị chuỗi rỗng):

~~~text
counting = [-3, -3, -1, 0, 2]
original = [-3, 2, -1, -3, 0]
radix = [-2147483648, -7, -1, 0, 7, 2147483647]
strings = [, a, a, aa, ab, aba, b, bat]
first is empty = true
UTF16 Z before a = true
unsupported = only a-z supported
~~~

### Giải thích vì sao mã đúng

- countingSortSigned kiểm tra mảng rỗng trước khi đọc input[0]; tính min/max trên chính dữ liệu, kiểm tra range bằng long trước khi cấp phát; chi phí O(n+R). Giới hạn MAX_COUNT_RANGE là **chính sách bảo vệ bộ nhớ cho ví dụ**, không phải giới hạn toán học của counting sort.
- Ở countingSortSigned, tổng tiền tố bao gồm và vòng duyệt ngược xác định chính xác chỗ đặt mỗi phần tử. Với các bản ghi gắn cùng một khóa, chính cơ chế ấy sẽ duy trì thứ tự các bản ghi nếu thuật toán phân phối toàn bản ghi thay vì chỉ mảng int.
- radixSortSigned chỉ thay đổi biểu diễn khóa khi lấy digit, không làm thay đổi x; sau bốn lượt ổn định, thứ tự theo khóa không dấu sau XOR chính là thứ tự int tăng dần. Các trường hợp âm cực trị không dùng Math.abs nên tránh được tràn trị tuyệt đối.
- lsdLowercase kiểm tra mọi ký tự thuộc alphabet trước khi dùng digit; ký tự tại vị trí thiếu nhận EOS=0. Mỗi lượt phân phối ổn định, nên kết quả là thứ tự từ điển trên a..z kể cả khóa độ dài khác nhau. Hai bản sao "a" vẫn xuất hiện hai lần.
- Ba hàm đều **không sửa mảng đầu vào**. Điều này tiêu thụ bộ nhớ đầu ra O(n), nhưng giúp hợp đồng API dễ kiểm thử.
- Java String.compareTo so các đơn vị UTF-16, nên ví dụ "Z" < "a" đúng theo thứ tự mã; hàm lsdLowercase **cố ý từ chối** "é" để không tuyên bố hỗ trợ ngữ nghĩa Unicode chưa được thiết kế.

### Phân tích chi phí

| Hàm | Thời gian | Bộ nhớ phụ (gồm đầu ra) | Điều kiện |
| --- | --- | --- | --- |
| countingSortSigned | O(n+R) | O(n+R) | R≤1.000.000 theo chính sách ví dụ |
| radixSortSigned | O(4(n+256)) | O(n+256) | int 32 bit, bốn lượt stable |
| lsdLowercase | O(L(n+27) + tổng độ dài kiểm tra) | O(n+27) | chỉ chữ thường a..z, L là độ dài tối đa |

LSD chuỗi có thể tốn công với dữ liệu rất lệch độ dài vì mọi chuỗi tham gia mỗi vị trí cho đến L; nếu nhiều chuỗi ngắn và một chuỗi cực dài, cân nhắc MSD hoặc sắp xếp so sánh.

## 10. So sánh phương án cho các dữ liệu khác nhau

| Dữ liệu và mục tiêu | Phương án phù hợp | Tránh điều gì? |
| --- | --- | --- |
| Một triệu số nguyên thuộc [-100,100] | Counting sort với offset 100; R=201 | Không dùng count[x] khi x âm |
| Một triệu số int bất kỳ, cần tăng dần | Radix 4 lượt byte với XOR bit dấu, hoặc thuật toán so sánh | Không cấp phát count phủ toàn bộ miền 32 bit |
| Bản ghi có score âm và cần giữ thứ tự id cùng score | Counting sort **ổn định** nếu R nhỏ; radix ổn định nếu miền lớn | Không dùng phân phối không ổn định |
| Chuỗi "a", "aa", "ab" và "" trên alphabet a..z | LSD stable với EOS=0 hoặc MSD kết thúc chuỗi | Không đệm bằng ký tự lớn |
| Các chuỗi số "2","10","0010" cần **thứ tự số** | Chuẩn hóa rồi sắp theo độ dài/chữ số với tie rule; hoặc kiểu số nếu trong miền | Không dùng thứ tự ký tự như thứ tự số |
| Tên tiếng Việt cần thứ tự ngôn ngữ tự nhiên | Collator phù hợp locale, kiểm thử quy tắc dấu/hoa-thường | Không coi raw UTF-16 hoặc ASCII là thứ tự tên |
| Chuỗi Unicode cần thứ tự code point | Tách code point và chọn thuật toán theo code point | Không đồng nhất charAt với code point |
| Số thực phân bố đều trên khoảng hữu hạn | Bucket sort nếu ánh xạ/biên và xử lý nhóm đúng | Không bỏ quên x=max, NaN, infinity |
| Mảng rất nhỏ hoặc miền khóa không biết | Sắp xếp so sánh thông thường | Không triển khai radix/counting quá phức tạp |

**Quy tắc thực hành:** bắt đầu bằng bộ so sánh tham chiếu rõ ràng để biết đầu ra mong đợi; chỉ chuyển sang thuật toán phân phối khi có lợi ích hiệu năng/bộ nhớ đủ lớn và đã chứng minh được ánh xạ bucket/digit **bảo toàn chính thứ tự tham chiếu đó**.

## 11. Những lỗi phổ biến và cách phát hiện

1. **Dùng số âm trực tiếp làm chỉ số count:** gây ngoại lệ; dùng offset từ min và kiểm tra tràn khi trừ.
2. **Cấp phát theo max-min bằng int:** với giá trị cực trị có thể tràn; tính range bằng long, kiểm tra dung lượng trước.
3. **Dùng Math.abs trên Integer.MIN_VALUE:** kết quả vẫn âm; cần tính độ lớn ở long hoặc dùng bit-sign transform.
4. **Radix sort int có dấu như unsigned mà không biến đổi bit dấu:** số âm sẽ xuất hiện sau số không âm khi sắp tăng dần.
5. **Phân phối radix không ổn định:** lượt sau phá thứ tự digit của lượt trước, nên kết quả sai dù từng lượt trông như đã “được sắp”.
6. **Lấy digit bằng phép % khi số âm mà không xử lý dấu:** chỉ số bucket có thể âm; không coi phần dư của số âm là chữ số 0..b-1.
7. **Đệm chuỗi thiếu vị trí bằng ký tự tùy ý:** "a" có thể đứng sai so với "aa"; dùng EOS nhỏ hơn mọi ký tự trong alphabet.
8. **Giả định mọi chuỗi cùng độ dài:** truy cập s.charAt(position) khi position≥s.length gây lỗi; kiểm tra độ dài trước.
9. **Nhầm thứ tự số và thứ tự từ điển:** "10" trước "2" theo ký tự nhưng sau "2" theo giá trị số.
10. **Giả định String.length() bằng số ký tự nhìn thấy:** Unicode có surrogate pair và dấu tổ hợp; char và code point không hoàn toàn tương đương.
11. **Dùng thứ tự ký tự theo mã để sắp tên tiếng Việt:** kết quả có thể trái quy tắc ngôn ngữ; chọn collation đúng đặc tả.
12. **Bỏ qua phần tử cực đại khi chia bucket:** x=max có thể sinh chỉ số k, vượt mảng bucket 0..k-1; chặn hoặc xử lý biên.
13. **Tuyên bố mọi bucket sort O(n):** chi phí phụ thuộc phân bố và cách sắp từng bucket.
14. **Không kiểm thử giữ nguyên đa tập và tính ổn định:** kết quả nhìn có vẻ tăng dần vẫn có thể làm mất bản ghi hoặc đảo thứ tự khóa bằng nhau.

## 12. Kiểm thử theo thuộc tính và bộ ca biên

### Bất biến chung

- **Bảo toàn đa tập:** mọi giá trị/bản ghi xuất hiện đúng số lần ở đầu ra như đầu vào.
- **Tính thứ tự:** sau sắp theo khóa, key(out[i]) ≤ key(out[i+1]) theo **comparator đã chọn**, không phải so bằng trực giác.
- **Ổn định nếu được yêu cầu:** hai bản ghi có khóa bằng nhau giữ thứ tự tương đối từ đầu vào.
- **Phạm vi digit:** mọi digit dùng làm chỉ số phải nằm trong [0,b-1].
- **Với LSD:** mỗi lượt ổn định và sau lượt thứ j, dãy được sắp theo j chữ số ít quan trọng nhất đã xử lý.
- **Với radix số có dấu:** thứ tự unsigned của (value ^ Integer.MIN_VALUE) phải trùng thứ tự signed của value.
- **Với chuỗi:** nếu s là tiền tố đúng của t, s phải xuất hiện trước t trong thứ tự từ điển.

### Ca kiểm thử gợi ý

| Đầu vào | Kết quả hoặc hành vi phải kiểm tra |
| --- | --- |
| [] | Ba hàm trong ví dụ trả mảng rỗng |
| [-3,2,-1,-3,0] | [-3,-3,-1,0,2] |
| [Integer.MIN_VALUE,0,Integer.MAX_VALUE,-1] | [Integer.MIN_VALUE,-1,0,Integer.MAX_VALUE] bằng radix |
| [-1,-1,-1] | Bảo toàn đủ ba bản sao |
| [1,1,1] | Counting sort với R=1 hoạt động |
| [Integer.MIN_VALUE,Integer.MAX_VALUE] với countingSortSigned | Báo miền quá rộng; không cấp phát mảng khổng lồ |
| ["a","aa","ab",""] | ["","a","aa","ab"] |
| ["b","bat","a","a"] | ["a","a","b","bat"], không mất phần tử trùng |
| ["Z"] hoặc ["é"] với lsdLowercase | Từ chối vì nằm ngoài alphabet a..z |
| Null array hoặc phần tử chuỗi null | Được từ chối bởi Objects.requireNonNull |
| Chuỗi số ["2","10"] | Thứ tự số khác thứ tự từ điển, phải chọn đặc tả |
| U+1F600 và U+E000 | Dùng thử để phát hiện khác biệt thứ tự UTF-16 so với code point |

Có thể sinh dãy int ngẫu nhiên (gồm số âm và phần tử trùng), so sánh kết quả radixSortSigned với bản sao đã chạy Arrays.sort. Với countingSortSigned, chỉ kiểm tra những dãy có range trong giới hạn đã công bố. Với lsdLowercase, so sánh với Arrays.sort trên bản sao gồm chuỗi a..z và chuỗi rỗng; hai thuật toán phải cho cùng thứ tự từ điển trong miền được hỗ trợ.

### Bài tập tự luyện

1. Tự viết counting sort ổn định cho bản ghi (score,id) có score từ -5 đến 5. Xác minh id của các bản ghi trùng score giữ thứ tự gốc.
2. Với [-10,-1,0,4,-2], liệt kê thứ tự sau khi dùng khóa x ^ Integer.MIN_VALUE và giải thích vì sao cả bốn lượt byte cần ổn định.
3. Mô phỏng LSD radix sort trên ["ab","a","b","", "aba"] với EOS=0, a=1, b=2. Viết danh sách sau mỗi vị trí xử lý từ phải sang trái.
4. Cho chuỗi số ["2","10","02","-10","-2"]. Nêu cách sắp theo **số** và theo **ký tự**; quy định rõ cách xử lý "02" và "2" bằng giá trị.
5. Tìm lý do "😀" (U+1F600) so với U+E000 có thể cho kết quả khác nhau theo UTF-16 và theo code point. Nếu bài toán là sắp tên tiếng Việt, giải thích vì sao chỉ áp dụng thứ tự code point vẫn chưa đủ.
6. Thiết kế bucket sort trên khoảng [-20,20] với bucket độ rộng 10; xác định bucket cho mọi phần tử, kể cả -20, -1, 0, 20 và phần tử nằm đúng ranh giới.
7. Dự đoán chi phí counting sort khi n=1.000 và R=10, R=10^6, R=2^32; từ đó chọn thuật toán phù hợp thay vì dựa vào nhãn “tuyến tính”.

**Kết luận:** trong sắp xếp phân phối, tốc độ không thể tách khỏi **ngữ nghĩa của khóa**. Số âm cần phép ánh xạ không âm đúng và không tràn; chuỗi độ dài khác nhau cần quy tắc kết thúc khóa; thứ tự ký tự cần đặc tả rõ ASCII/UTF-16/code point/collation. Khi bảo đảm được các tính chất đó và mỗi lượt phân phối ổn định nơi cần thiết, counting sort, radix sort và bucket sort mới cho kết quả vừa đúng vừa hiệu quả.

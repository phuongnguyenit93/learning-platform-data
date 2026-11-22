# Biểu diễn và xử lý số nguyên vượt độ rộng máy

Một kiểu số nguyên có **độ rộng cố định** (ví dụ Java int 32-bit hoặc long 64-bit) chỉ biểu diễn được các giá trị trong một miền hữu hạn. Trong khi đó, các bài toán số học có thể yêu cầu cộng hai số dài hàng nghìn chữ số, nhân những số vượt xa Long.MAX_VALUE, tính lũy thừa chính xác hoặc xử lý dữ liệu định danh gồm nhiều chữ số mà **không được mất một đơn vị nào**.

Đó là lý do cần **số nguyên độ chính xác tùy ý (arbitrary-precision integer)**, thường gọi là **big integer**. Thay vì nhét cả số vào một từ máy, ta lưu nó bằng **nhiều chữ số hoặc nhiều khối (limbs)**, xử lý phép toán theo quy tắc nhớ khi cộng, mượn khi trừ và tích từng cặp khối khi nhân.

Bài thuộc **Thuật toán số học**, tập trung vào:

- Khi nào số nguyên vượt miền int/long và vì sao overflow nguy hiểm.
- Cách biểu diễn **dấu + độ lớn** theo những khối cơ số 10^9 đặt theo thứ tự **little-endian**.
- Chuẩn hóa số 0, bỏ số 0 đầu, phân tích/định dạng chuỗi số thập phân.
- So sánh trị tuyệt đối, cộng có nhớ, trừ có mượn, cộng/trừ số có dấu.
- Nhân theo thuật toán **schoolbook O(nm)** và chia cho số nguyên dương nhỏ bằng phép chia dài.
- Trường hợp phép chia/trả phần dư của số âm, modulo, ký hiệu cơ số, byte có dấu.
- Sử dụng **java.math.BigInteger** trong Java 17+, phân biệt với BigDecimal, double và long.
- Chứng minh tính đúng, phân tích độ phức tạp, ca biên, chương trình độc lập và chiến lược kiểm thử.

**Thông điệp:** độ chính xác tùy ý không có nghĩa vô hạn tài nguyên. Số được tạo từ nhiều khối vẫn cần RAM, thời gian xử lý và kiểm soát thuật toán tương ứng với số khối.

## 1. Giới hạn của số nguyên có độ rộng cố định

Trong Java:

| Kiểu | Số bit | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: | ---: |
| byte | 8 | −128 | 127 |
| short | 16 | −32768 | 32767 |
| int | 32 | −2147483648 | 2147483647 |
| long | 64 | −9223372036854775808 | 9223372036854775807 |

Đây là **số nguyên có dấu** theo biểu diễn two's complement. Miền long không đối xứng: có một giá trị âm hơn về trị tuyệt đối so với giá trị dương lớn nhất.

Ví dụ, số:

**9223372036854775808 = Long.MAX_VALUE + 1**

không biểu diễn được bằng long.

Nếu dùng phép cộng long thông thường:

~~~java
long x = Long.MAX_VALUE;
long y = x + 1L;
~~~

y sẽ **wrap around** thành Long.MIN_VALUE, không báo lỗi tự động. Các phép nhân cũng có thể wrap như vậy.

### BigInteger khắc phục gì?

Java **BigInteger** lưu độ lớn bằng nhiều word và lưu thêm dấu, nên có thể biểu diễn số lớn hơn long hàng tỷ lần, miễn còn tài nguyên.

~~~java
BigInteger x = new BigInteger("9223372036854775807");
BigInteger y = x.add(BigInteger.ONE);
System.out.println(y); // 9223372036854775808
~~~

### BigInteger không tự động làm long an toàn

Nếu phép tính đã được thực hiện **bằng long và overflow trước khi chuyển kiểu**, BigInteger chỉ nhận kết quả long **đã sai**.

Sai:

~~~java
long a = Long.MAX_VALUE;
BigInteger wrong = BigInteger.valueOf(a + 1);
~~~

Đúng:

~~~java
BigInteger correct =
        BigInteger.valueOf(Long.MAX_VALUE)
                  .add(BigInteger.ONE);
~~~

Muốn tính chính xác, cần **chuyển sang BigInteger trước khi thực hiện phép toán** vượt miền máy.

## 2. Mất chính xác khác overflow

Một số được biểu diễn sai có thể do nhiều nguyên nhân:

1. **Overflow kiểu nguyên**: vượt miền int/long khi cộng/nhân/dịch bit.
2. **Mất chính xác khi dùng floating point**: double không biểu diễn được mọi số nguyên lớn.
3. **Parse sai**: đọc giá trị lớn vào Long.parseLong gây NumberFormatException.
4. **Truyền dữ liệu bằng JSON/JavaScript Number**: một số nguyên có nhiều chữ số bị làm tròn trong quá trình trung gian.
5. **Cắt bỏ số 0 đầu**: đôi khi đây là điều đúng cho giá trị số, nhưng là sai với mã định danh cần giữ định dạng.

### Giới hạn độ chính xác của double và JavaScript Number

double dùng 53 bit độ chính xác significand. Nó biểu diễn chính xác **mọi số nguyên trong khoảng −(2^53) đến 2^53**, nhưng không biểu diễn được tất cả các số nguyên ngoài khoảng đó.

Ví dụ:

**9007199254740993 = 2^53+1**

không thể được lưu chính xác dưới dạng JavaScript Number thông thường.

Nếu dữ liệu là số nguyên toán học, JavaScript dùng **BigInt** hoặc truyền giá trị dưới dạng **chuỗi thập phân** và xử lý bằng thư viện phù hợp. Đừng cho một hệ thống trung gian chuyển thành double rồi mong khôi phục đủ các chữ số.

### Giá trị số khác định danh

Giá trị số "000123" và "123" đều bằng 123. Nhưng mã tài khoản hoặc mã giao dịch có thể quy định phải giữ đủ ký tự "000123".

**BigInteger lưu giá trị, không lưu định dạng gốc.** Nếu cần bảo toàn số 0 đầu hay dấu cộng ban đầu, hãy lưu một **String riêng**.

## 3. Mô hình biểu diễn bằng dấu và độ lớn

Ta cần hai thành phần:

- **sign**: −1 cho số âm, 0 cho số 0, +1 cho số dương.
- **magnitude**: một dãy các khối không âm biểu diễn trị tuyệt đối.

Chọn cơ số nội bộ:

**BASE = 10^9 = 1_000_000_000**.

Mỗi khối (limb) có giá trị từ **0 đến BASE−1**.

Dùng mảng **little-endian**, nghĩa là **khối có trọng số thấp nhất nằm ở chỉ số 0**:

**|x| = limb[0] + limb[1]·BASE + limb[2]·BASE² + ...**.

Ví dụ:

~~~text
x = 1234567890123456789012345678901234567890

Nhom tu phai sang trai (moi nhom 9 chu so):
1234 | 567890123 | 456789012 | 345678901 | 234567890

limbs little-endian:
[234567890, 345678901, 456789012, 567890123, 1234]
~~~

Số 0 sẽ có:

**sign=0**, **limbs=[]**.

Đây là biểu diễn **duy nhất, chuẩn hóa** của 0 trong chương trình.

### Vì sao đặt khối thấp trước?

Cộng/trừ/nhân kiểu giấy bút xử lý từ hàng đơn vị lên các hàng cao. Little-endian giúp:

- Bắt đầu từ chỉ số 0.
- Truyền carry/borrow sang chỉ số i+1.
- Không phải dịch cả mảng khi có nhớ.
- Nhân schoolbook dễ cập nhật vị trí i+j.

Khi in ra thập phân, ta đi từ **limb cao nhất xuống thấp nhất** và bổ sung số 0 đầu cho từng khối sau khối cao nhất.

## 4. Chọn cơ số 10, 10^9 hay 2^32?

### Một chữ số thập phân trên mỗi phần tử

Cách dễ hiểu nhất là mỗi phần tử chứa 0..9. Ví dụ 12345 lưu [5,4,3,2,1]. Dễ tính bằng tay nhưng cần nhiều phần tử và nhiều vòng lặp.

### Một khối cơ số 10^9

Mỗi int chứa tối đa chín chữ số, giúp giảm số phần tử khoảng 9 lần so với một chữ số mỗi phần tử.

Với hai limb <10^9, tích của chúng <10^18, vừa trong **long có dấu**. Điều này tạo ra một miền an toàn để nhân hai khối sau khi ép sang long.

Trong code:

~~~java
long product = (long) a[i] * b[j];
~~~

Điều kiện quan trọng là phải **ép sang long trước phép nhân**. Nếu viết a[i]*b[j] với cả hai đều int, phép nhân sẽ xảy ra ở int và overflow trước khi gán cho long.

### Cơ số 2^32 hoặc 2^64

Một thư viện BigInteger tối ưu thường dùng các word theo cơ số lũy thừa của 2, thuận tiện cho thao tác bit, nhân word và xử lý byte.

Nhưng khi xử lý unsigned word bằng kiểu primitive có dấu, cần chú ý phép dịch, carry và biểu diễn; cơ số 2^32 không có cùng cận tích đơn giản nếu tất cả trung gian đều là long có dấu.

Bài chọn **10^9** để minh họa và để chuyển đổi thập phân thuận tiện, không khẳng định đây là cơ số tối ưu của mọi thư viện.

## 5. Bất biến biểu diễn và chuẩn hóa

Một số BigDec hợp lệ cần thỏa:

1. Mọi limb nằm trong **[0,BASE−1]**.
2. Không có limb cao nhất bằng 0 nếu magnitude không rỗng.
3. Nếu magnitude rỗng thì sign=0.
4. Nếu magnitude không rỗng thì sign chỉ có thể −1 hoặc +1.
5. Không có hai biểu diễn khác nhau cho cùng giá trị 0 (ví dụ +0, −0, [0,0]).

### Trim số 0 ở phía cao

Sau phép trừ hoặc nhân, mảng kết quả có thể có limb 0 ở cuối. Ví dụ [5,0,0] vẫn chỉ biểu diễn 5.

Ta giảm độ dài hiệu dụng:

~~~java
int used = digits.length;
while (used > 0 && digits[used - 1] == 0) {
    used--;
}
digits = Arrays.copyOf(digits, used);
~~~

Nếu used=0, dấu phải đổi thành 0.

### Vì sao chuẩn hóa có ích?

- So sánh hai độ lớn có thể bắt đầu từ **số limb**.
- In ra chuỗi không sinh số 0 đầu không cần thiết.
- Kiểm tra zero đơn giản.
- Trừ hai số bằng nhau trả đúng một zero chuẩn.
- Các phép toán không cần xử lý âm 0 như một trường hợp riêng.

Việc chuẩn hóa là một **invariant của kiểu dữ liệu**, không chỉ công đoạn làm đẹp output.

## 6. Parse chuỗi thập phân rất dài

Với chuỗi số s, ta cần đọc mà **không dùng Long.parseLong cho toàn chuỗi**.

Quy trình:

1. Kiểm tra s không rỗng và khác null.
2. Đọc dấu '-' hoặc '+' ở đầu nếu có.
3. Kiểm tra các ký tự còn lại đều là chữ số ASCII '0'..'9'.
4. Bỏ các số 0 đầu về mặt **giá trị**.
5. Nếu không còn chữ số nào, trả zero chuẩn.
6. Từ phải sang trái, cắt mỗi nhóm tối đa **9 chữ số**.
7. Phân tích từng nhóm nhỏ bằng Integer.parseInt, an toàn vì nhóm <10^9.
8. Đặt các nhóm vào mảng little-endian.

Ví dụ:

~~~text
input = -0001234567890123

Bo dau tru va so 0 dau:
1234567890123

Nhom 9 chu so tu phai:
1234 | 567890123

sign  = -1
limbs = [567890123, 1234]
~~~

### Không tự trim khoảng trắng nếu API không cho phép

Chương trình từ chối chuỗi chứa khoảng trắng, dấu phẩy, dấu gạch dưới hoặc chữ cái. Đây là hợp đồng parse **chuỗi thập phân thuần**.

Nếu input có dấu phân cách hàng nghìn hoặc định dạng locale, cần xử lý chúng ở một lớp riêng trước khi gọi parse, không âm thầm chấp nhận mọi ký tự.

### Độ phức tạp parse

Với D chữ số thập phân, mỗi ký tự được kiểm tra một lần và các nhóm có kích thước ≤9 được đọc một lần:

**O(D) thời gian**, khoảng **O(D/9) limb**.

## 7. Chuyển từ mảng limb thành chuỗi

Để xuất số:

1. Nếu sign=0, trả **"0"**.
2. Nếu sign<0, thêm dấu '-'.
3. In limb cao nhất như số thập phân bình thường, không thêm số 0 đầu.
4. Với mỗi limb còn lại theo thứ tự giảm dần, in **đúng 9 chữ số**, bổ sung '0' phía trước nếu cần.

Ví dụ:

~~~text
limbs = [5, 3, 12]
BASE  = 10^9

Khối cao nhất: "12"
Khối tiếp:      "000000003"
Khối thấp nhất: "000000005"

Output:
12000000003000000005
~~~

Nếu không bổ sung 0 đủ 9 chữ số, cùng một mảng có thể in ra sai độ lớn. Ví dụ limb [5,3] đại diện cho:

**3·10^9+5=3000000005**, không phải "35".

Định dạng output có độ phức tạp **O(D)** theo số chữ số in.

## 8. So sánh trị tuyệt đối và số có dấu

Giả sử hai độ lớn A và B đều chuẩn hóa.

Để so sánh |A| và |B|:

1. Nếu số limb khác nhau, số có **nhiều limb hơn** có độ lớn lớn hơn.
2. Nếu cùng số limb, so từ **limb cao nhất** xuống thấp nhất.
3. Ở limb đầu tiên khác nhau, giá trị limb lớn hơn quyết định độ lớn.
4. Nếu mọi limb bằng nhau, hai độ lớn bằng nhau.

Với số có dấu:

- Số âm luôn nhỏ hơn 0 và số dương.
- 0 nhỏ hơn số dương, lớn hơn số âm.
- Hai số dương: dùng compareMagnitude.
- Hai số âm: **đảo chiều** kết quả compareMagnitude.

Ví dụ:

~~~text
Compare(+123, +45) -> +1
Compare(-123, -45) -> -1
Compare(-0, 0)    ->  0  (zero chuan)
~~~

So sánh cần **O(max(L_A,L_B))** trong trường hợp xấu, với L là số limb.

### equals và hashCode

Nếu tự xây một kiểu số bất biến dùng làm key trong HashMap/HashSet, nên triển khai **equals() và hashCode()** dựa trên dấu và mảng limb đã chuẩn hóa. Không thể dùng toán tử **==** để so nội dung hai object Java.

Trong code Java, mảng limb được sao chép khi tạo object, trường dữ liệu là final và không bị chỉnh sửa bên ngoài; vì thế kiểu số được trình bày là **immutable**.

## 9. Cộng độ lớn: carry theo từng khối

Cho hai độ lớn A,B không âm với các limb little-endian.

Ở vị trí i, tính:

**sum = a[i] + b[i] + carry**,

với limb không tồn tại được xem là 0.

Sau đó:

**result[i] = sum mod BASE**.

**carry = floor(sum/BASE)**.

Cuối cùng, nếu carry>0, thêm limb mới.

### Ví dụ

Dùng BASE=100 để dễ nhìn (khác BASE=10^9 trong code), hai số:

~~~text
A = 9999  -> limbs [99,99]
B = 1     -> limbs [1]

i=0: 99+1 = 100 -> digit 0, carry 1
i=1: 99+0+1 =100 -> digit 0, carry 1
Cuoi: carry 1

result limbs [0,0,1]
result = 10000
~~~

### Cận trung gian

Vì mỗi limb ≤BASE−1 và carry≤1:

**sum≤2·BASE−1**.

Với BASE=10^9, sum<2·10^9, vừa trong long; bản demo dùng long để nhất quán và tránh bẫy toán tử int.

Độ phức tạp cộng: **O(max(L_A,L_B))**.

## 10. Trừ độ lớn: borrow theo từng khối

Giả sử đã xác định **A≥B≥0**.

Tại vị trí i:

**difference = a[i] − b[i] − borrow**.

Nếu difference<0:

- Cộng BASE vào difference.
- Đặt borrow=1.

Nếu difference≥0:

- borrow=0.

Lưu difference vào result[i].

### Ví dụ

Với BASE=100:

~~~text
A = 10000 -> limbs [0,0,1]
B = 1     -> limbs [1]

i=0: 0-1 = -1 -> 99, borrow 1
i=1: 0-0-1 = -1 -> 99, borrow 1
i=2: 1-0-1 =  0 -> 0, borrow 0

result [99,99,0], trim -> [99,99]
result = 9999
~~~

Hàm trừ độ lớn chỉ được gọi khi **A≥B**. Nếu gọi ngược, borrow cuối có thể không bằng 0 và kết quả không hợp lệ. Với hai số có dấu, trước tiên cần dùng phép so trị tuyệt đối để xác định hướng trừ.

Độ phức tạp trừ: **O(L_A)** khi A≥B.

## 11. Cộng và trừ hai số có dấu

Cho A=s_A·|A| và B=s_B·|B|.

### Cộng

- Nếu A=0, trả B.
- Nếu B=0, trả A.
- Nếu hai dấu bằng nhau, **cộng trị tuyệt đối** rồi giữ dấu chung.
- Nếu khác dấu, **trừ trị tuyệt đối nhỏ khỏi lớn** và lấy dấu của số có trị tuyệt đối lớn hơn.
- Nếu hai trị tuyệt đối bằng nhau và dấu trái nhau, kết quả là zero chuẩn.

Ví dụ:

~~~text
(+700) + (+80) = +780
(-700) + (-80) = -780
(+700) + (-80) = +620
(-700) + (+80) = -620
(+700) + (-700) = 0
~~~

### Trừ

**A−B=A+(-B)**.

Để triển khai, viết negate() thay đổi dấu (trừ zero) rồi dùng phép add đã chứng minh đúng.

### Các trường hợp cần thử

- A+B với A,B rất lớn.
- A+(-A)=0, không tạo âm 0.
- A−A=0.
- A−B khi B>A.
- A+B khi A âm, B dương và |A|<|B|.
- A+B khi A âm, B dương và |A|>|B|.

Không được xử lý cộng trừ có dấu bằng cách chỉ cộng/trừ mảng limb mà bỏ qua dấu.

## 12. Nhân schoolbook trên các khối

Với:

**A=Σ a[i]·BASE^i**, **B=Σ b[j]·BASE^j**,

ta có:

**A·B=ΣᵢΣⱼ a[i]·b[j]·BASE^(i+j)**.

Do đó tích của hai limb i,j đóng góp vào vị trí **i+j** của mảng kết quả.

Quy trình:

1. Tạo mảng result có **L_A+L_B** limb bằng 0.
2. Với mỗi limb a[i], nhân lần lượt với mọi limb b[j].
3. Tại vị trí i+j, cộng tích đó với giá trị result đã có và carry.
4. Lưu **cur mod BASE** tại result[i+j], carry=cur/BASE.
5. Sau vòng j, truyền carry sang vị trí i+L_B, có thể lan tiếp nếu cần.
6. Chuẩn hóa số 0 cao và gắn dấu s_A·s_B.

### Cận an toàn trên long

Trong vòng nhân, mỗi thành phần thỏa:

- 0≤result[i+j]≤BASE−1.
- 0≤a[i],b[j]≤BASE−1.
- 0≤carry≤BASE−1.

Vì vậy:

**cur≤(BASE−1)²+(BASE−1)+(BASE−1)=BASE²−1**.

Với BASE=10^9:

**cur≤10^18−1 < Long.MAX_VALUE**.

Như vậy phép nhân và cộng trong **long** an toàn khi dùng đúng cận. Nếu chuyển BASE lên 10^10 mà vẫn dùng long có dấu, chứng minh này không còn đúng.

### Ví dụ nhân số âm

~~~text
(-123) * 45 = -5535
(-123) * (-45) = 5535
0 * 12345678901234567890 = 0
~~~

Dấu được quyết định **sau khi tính tích trị tuyệt đối**. Không phải nhân từng limb âm; các limb luôn không âm.

### Độ phức tạp

Nếu A có L_A limb và B có L_B limb, thuật toán schoolbook cần:

**O(L_A·L_B)** phép nhân limb.

Với hai số có cùng L limb: **O(L²)**.

Các thư viện big integer hiệu năng cao có thể dùng Karatsuba, Toom–Cook hoặc FFT/NTT khi số đủ lớn, nhưng **schoolbook** đơn giản, dễ xác minh và phù hợp để học nguyên lý.

## 13. Chia dài cho số nguyên dương nhỏ

Phép chia **số lớn cho số nguyên dương nhỏ** là bước quan trọng để tính thương và phần dư hoặc chuyển đổi cơ số.

Giả sử số bị chia A có limbs little-endian và số chia d>0 nằm trong int. Ta duyệt **từ limb cao nhất xuống thấp nhất**, giữ phần dư rem của phần đã xử lý:

**cur = rem·BASE + a[i]**.

Sau đó:

**quotient[i] = floor(cur/d)**.

**rem = cur mod d**.

Bất biến: sau khi đã xử lý prefix ở những khối cao, phần giá trị prefix bằng:

**d·prefixQuotient + rem**, với 0≤rem<d.

### Vì sao cur vừa long?

Với d là int dương:

**0≤rem<d≤2^31−1** và **a[i]<BASE**.

Do đó:

**cur<d·BASE≤(2^31−1)·10^9 < Long.MAX_VALUE**.

Phép tính trong long an toàn với BASE=10^9.

### Vì sao quotient limb nhỏ hơn BASE?

Từ cur<d·BASE, suy ra:

**floor(cur/d)<BASE**.

Vậy quotient[i] vẫn là một limb hợp lệ.

### Quy tắc dấu của thương và phần dư

Bài dùng quy tắc **chia nguyên cắt về 0**, tương thích với Java BigInteger.divideAndRemainder cho số chia dương:

- quotient có dấu của số bị chia (nếu khác 0).
- remainder có dấu của số bị chia (nếu khác 0).
- **A=d·quotient+remainder**.
- **|remainder|<d**.

Ví dụ:

~~~text
-100 / 7 -> quotient = -14, remainder = -2
-100 = 7*(-14) + (-2)
~~~

Đây **không phải** phép modulo chuẩn luôn trả dư không âm. Với modulo d>0, phần dư chuẩn của -100 là 5; với phép chia remainder như trên là -2.

Nếu bài yêu cầu **mod không âm**, ta có thể chuẩn hóa remainder bằng công thức toán học phù hợp.

## 14. So sánh một ví dụ nhiều chữ số

Cho:

~~~text
A = 1234567890123456789012345678901234567890
B = 987654321098765432109876543210
~~~

Hai số đều vượt giới hạn long rất xa.

Kết quả:

~~~text
A+B =
1234567891111111110111111111011111111100

A-B =
1234567889135802467913580246791358024680

B-A =
-1234567889135802467913580246791358024680

A*B =
1219326311370217952261850327337448559633622923332237463801111263526900

A/97 quotient =
12727504021891307103220058545373552246

A/97 remainder =
28
~~~

Thử phép chia ngược dấu:

~~~text
(-A)/97 quotient =
-12727504021891307103220058545373552246

(-A)/97 remainder =
-28
~~~

Kiểm chứng độc lập:

**A = 97·quotient + 28**.

Với -A:

**-A = 97·(−quotient) − 28**.

### Vì sao ví dụ này có ích?

Các kết quả gồm:

- Cộng tạo nhớ qua nhiều khối.
- Trừ với nhiều lần mượn.
- Nhân tích hai số khác độ dài.
- Thương và phần dư có dấu theo quy tắc Java.
- Nhiều chữ số vượt giới hạn của int, long và double chính xác.

Nên sử dụng **BigInteger** làm oracle độc lập cho cách cài mảng limb, thay vì tự kiểm chứng bằng chính thuật toán mảng limb đó.

## 15. BigInteger trong Java 17+

Lớp **java.math.BigInteger** đã triển khai số nguyên độ chính xác tùy ý và nhiều thuật toán số học được tối ưu. Hầu hết bài thực tế trên Java nên dùng thư viện thay vì tự viết big integer, trừ khi đề yêu cầu cài đặt cơ chế hoặc ngôn ngữ bị hạn chế.

### Tạo từ chuỗi và giá trị nguyên

~~~java
BigInteger a =
        new BigInteger("123456789012345678901234567890");
BigInteger b = BigInteger.valueOf(97L);
~~~

Không cần nối qua Long.parseLong. Nếu string vượt miền long, **new BigInteger(String)** vẫn đọc được.

Các phương thức phổ biến:

| Phương thức | Ý nghĩa |
| --- | --- |
| add(b) | Cộng |
| subtract(b) | Trừ |
| multiply(b) | Nhân |
| divide(b) | Chia lấy thương cắt về 0 |
| remainder(b) | Phần dư theo phép chia có dấu |
| divideAndRemainder(b) | Cả thương và dư |
| mod(m) | Phần dư không âm, yêu cầu m>0 |
| gcd(b) | Ước chung lớn nhất không âm |
| pow(int n) | Lũy thừa nguyên, n không âm và kiểu int |
| modPow(e,m) | Lũy thừa modulo |
| modInverse(m) | Nghịch đảo modulo khi tồn tại |
| shiftLeft(k), shiftRight(k) | Dịch bit theo số học BigInteger |
| bitLength() | Độ dài bit của biểu diễn tối thiểu theo hợp đồng API |
| toString(radix) | Xuất cơ số 2..36 |
| compareTo(b), equals(b) | So thứ tự hoặc bằng nhau theo giá trị |

### BigInteger bất biến

BigInteger là **immutable**:

~~~java
BigInteger x = BigInteger.TEN;
x.add(BigInteger.ONE);      // X van la 10.
x = x.add(BigInteger.ONE);  // X moi thanh 11.
~~~

Các method tạo **kết quả mới**, không sửa object hiện tại.

**Không dùng == để so giá trị BigInteger.** Dùng equals hoặc compareTo:

~~~java
if (x.equals(y)) { /* equal values */ }
if (x.compareTo(y) > 0) { /* x greater */ }
~~~

### Những phép tính dễ bị giới hạn bởi API

- BigInteger.pow nhận **int exponent**, không nhận số mũ BigInteger tùy ý.
- BigInteger.modPow nhận BigInteger exponent/modulus nhưng phải thỏa điều kiện API tương ứng.
- BigInteger.intValue() và longValue() có thể **cắt bỏ bit cao** nếu kết quả không vừa primitive.
- Dùng **intValueExact()** hoặc **longValueExact()** nếu muốn ném lỗi khi mất thông tin.

## 16. Phân biệt BigInteger và BigDecimal

**BigInteger** biểu diễn **số nguyên**, không lưu phần thập phân.

**BigDecimal** biểu diễn số thập phân chính xác với **unscaled value** và **scale**, phù hợp khi cần giữ số chữ số thập phân theo hợp đồng, ví dụ tiền tệ.

Ví dụ:

~~~text
BigInteger("10000000000000000000")
-> So nguyen 10^19.

BigDecimal("123.4500")
-> Gia tri so thap phan, co scale=4.
~~~

Không dùng BigInteger cho số tiền có phần xu nếu không tự biểu diễn bằng số **đơn vị nhỏ nhất** (ví dụ đồng xu) và quản lý scale bên ngoài.

Không dùng double làm nguồn dữ liệu cho BigDecimal nếu mục tiêu là bảo toàn một chuỗi thập phân cụ thể. Nên dùng:

~~~java
new BigDecimal("0.1")
~~~

thay vì cố suy ra chính xác giá trị thập phân gốc từ kết quả một phép floating-point đã làm tròn.

### Phép chia không tròn của BigInteger

**BigInteger.divide()** thực hiện chia nguyên lấy thương, không trả kết quả phân số. Nếu cần giá trị hữu tỉ chính xác như 1/3, dùng cặp **tử số/mẫu số BigInteger** đã rút gọn.

Nếu chỉ cần decimal có giới hạn chữ số, dùng BigDecimal.divide với scale và RoundingMode phù hợp, không mặc định phép chia nào cũng có biểu diễn thập phân hữu hạn.

## 17. Cơ số 2,16,36 và chuyển đổi qua chuỗi

Một số nguyên là **giá trị**, có thể có nhiều biểu diễn:

~~~text
Decimal: 255
Binary : 11111111
Hex    : ff
~~~

BigInteger hỗ trợ:

~~~java
BigInteger x = new BigInteger("FF", 16); // 255
String binary = x.toString(2);          // "11111111"
String hex = x.toString(16);            // "ff"
~~~

Lớp BigDec trong bài chỉ nhận chuỗi thập phân vì ưu tiên minh họa xử lý base 10^9. Nếu cần parse hexadecimal hoặc binary bằng tay, có thể xử lý từng chữ số:

**value = value·radix + digit**.

Để xuất cơ số radix, có thể chia dài lặp lại cho radix và lấy các phần dư theo thứ tự ngược.

### Decimal digits và bit length

Một số nguyên có D chữ số thập phân thường cần xấp xỉ:

**D·log₂(10) ≈ 3.322D bit**.

Ví dụ A có 40 chữ số thập phân, bit length chính xác là **130**.

Số 2^128 có **129 bit** trong biểu diễn dương vì có một bit 1 ở vị trí chỉ số 128, rồi 128 bit 0.

### Endianness

Trong mã BigDec, little-endian là **thứ tự limb trong mảng Java**, không phải endianness của CPU hoặc thứ tự byte truyền qua mạng.

Nếu serialize sang byte, phải quyết định rõ **thứ tự byte**, dấu, độ rộng và padding. Không nên trộn lẫn mảng limb nội bộ với giao thức truyền dữ liệu mà không có quy định.

## 18. Byte, dấu và biểu diễn two's complement

Java BigInteger lưu và xuất byte theo hợp đồng API:

**toByteArray() trả biểu diễn two's-complement, big-endian** có độ dài cần thiết.

Điều này có hai hệ quả:

1. Số dương mà bit cao nhất của byte đầu tiên là 1 có thể cần **một byte 0 ở đầu** để tránh bị hiểu là số âm.
2. Số âm sử dụng two's complement, không phải một byte dấu riêng và các byte độ lớn không âm.

Để đọc một byte[] thành **số dương theo unsigned magnitude**, Java có constructor:

~~~java
BigInteger positive = new BigInteger(1, bytes);
~~~

Còn:

~~~java
BigInteger signed = new BigInteger(bytes);
~~~

diễn giải các byte theo two's complement có dấu.

### Vì sao quan trọng?

Một hash, ID nhị phân, khóa công khai hay giá trị từ giao thức mạng có thể được biểu diễn dưới dạng byte[] không dấu. Nếu đưa các byte đó trực tiếp vào new BigInteger(bytes), kết quả có thể bị diễn giải thành số **âm**.

Với dữ liệu cần giữ nguyên số byte hoặc số 0 đầu, **BigInteger.toByteArray() không bảo đảm giữ đúng số byte ban đầu**. Muốn encode theo độ rộng cố định, phải padding hoặc cắt byte dấu có kiểm tra, không tự giả định round-trip byte-for-byte.

### Lưu ý về mật mã

BigInteger là một công cụ số học, không phải bằng chứng rằng mọi thuật toán dựa trên nó đều an toàn. Một triển khai ký số, mã hóa hoặc xử lý khóa còn cần thuật toán và thư viện mật mã chuẩn, random phù hợp và kiểm soát side channel.

Không tự viết mật mã bằng cộng/trừ/nhân BigInteger rồi coi là an toàn chỉ vì có số rất lớn.

## 19. Java 17+ hoàn chỉnh: tự biểu diễn và đối chiếu BigInteger

Chương trình dưới đây dùng **BigDec** là một kiểu số nguyên có dấu và trị tuyệt đối biểu diễn bằng **int[] limbs little-endian, BASE=10^9**.

Nó triển khai:

- **parse** và **toString** cho chuỗi thập phân dài, dấu +/- và số 0 đầu.
- **compareTo**, **equals**, **hashCode**, **negate**.
- **add** và **subtract**, xử lý dấu, carry, borrow.
- **multiply** theo schoolbook O(nm).
- **divideByPositiveInt** trả thương và phần dư có dấu theo kiểu chia cắt về 0.
- Ví dụ dữ liệu dài, chuẩn hóa âm 0, cộng/nhân số âm.
- Các phép toán BigInteger: cộng vượt long, lũy thừa 2^100, modPow, gcd, remainder/mod, bitLength, đổi cơ số và byte sign round-trip.

**Tệp:** HugeIntegerRepresentationDemo.java

~~~java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Objects;

public class HugeIntegerRepresentationDemo {

    static final int BASE = 1_000_000_000;

    record DivRem(BigDec quotient, long remainder) {}

    static final class BigDec implements Comparable<BigDec> {
        static final BigDec ZERO =
                new BigDec(0, new int[0]);

        final int sign;   // -1, 0 or +1
        final int[] limbs; // least significant limb first

        private BigDec(int requestedSign, int[] values) {
            int length = values.length;
            while (length > 0 && values[length - 1] == 0) {
                length--;
            }

            limbs = Arrays.copyOf(values, length);
            sign = length == 0 ? 0 :
                    (requestedSign < 0 ? -1 : 1);
        }

        static BigDec parse(String s) {
            Objects.requireNonNull(s, "number");

            if (s.isEmpty()) {
                throw new NumberFormatException("Empty number");
            }

            int sign = 1;
            int pos = 0;

            if (s.charAt(0) == '-' || s.charAt(0) == '+') {
                if (s.charAt(0) == '-') sign = -1;
                pos = 1;
            }

            if (pos == s.length()) {
                throw new NumberFormatException("Missing digits");
            }

            for (int i = pos; i < s.length(); i++) {
                char c = s.charAt(i);
                if (c < '0' || c > '9') {
                    throw new NumberFormatException(
                            "Only ASCII decimal digits");
                }
            }

            while (pos < s.length()
                    && s.charAt(pos) == '0') {
                pos++;
            }
            if (pos == s.length()) return ZERO;

            int count = (s.length() - pos + 8) / 9;
            int[] digits = new int[count];

            int index = 0;
            for (int end = s.length(); end > pos; end -= 9) {
                int from = Math.max(pos, end - 9);
                digits[index++] = Integer.parseInt(
                        s.substring(from, end));
            }

            return new BigDec(sign, digits);
        }

        @Override
        public String toString() {
            if (sign == 0) return "0";

            StringBuilder sb = new StringBuilder();
            if (sign < 0) sb.append('-');

            sb.append(limbs[limbs.length - 1]);

            for (int i = limbs.length - 2; i >= 0; i--) {
                String chunk = Integer.toString(limbs[i]);
                for (int j = chunk.length(); j < 9; j++) {
                    sb.append('0');
                }
                sb.append(chunk);
            }

            return sb.toString();
        }

        private static int compareAbs(int[] a, int[] b) {
            if (a.length != b.length) {
                return Integer.compare(a.length, b.length);
            }

            for (int i = a.length - 1; i >= 0; i--) {
                if (a[i] != b[i]) {
                    return Integer.compare(a[i], b[i]);
                }
            }

            return 0;
        }

        @Override
        public int compareTo(BigDec other) {
            Objects.requireNonNull(other, "other");

            if (sign != other.sign) {
                return Integer.compare(sign, other.sign);
            }
            if (sign == 0) return 0;

            return sign * compareAbs(limbs, other.limbs);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BigDec x
                    && sign == x.sign
                    && Arrays.equals(limbs, x.limbs);
        }

        @Override
        public int hashCode() {
            return 31 * sign + Arrays.hashCode(limbs);
        }

        BigDec negate() {
            if (sign == 0) return this;
            return new BigDec(-sign, limbs);
        }

        private static int[] addAbs(int[] a, int[] b) {
            int length = Math.max(a.length, b.length);
            int[] out = new int[length + 1];

            long carry = 0;
            for (int i = 0; i < length; i++) {
                long x = i < a.length ? a[i] : 0;
                long y = i < b.length ? b[i] : 0;

                long sum = x + y + carry;
                out[i] = (int) (sum % BASE);
                carry = sum / BASE;
            }
            out[length] = (int) carry;
            return out;
        }

        // Requires |a| >= |b|.
        private static int[] subtractAbs(
                int[] a, int[] b) {
            int[] out = new int[a.length];
            long borrow = 0;

            for (int i = 0; i < a.length; i++) {
                long x = a[i];
                long y = i < b.length ? b[i] : 0;

                long diff = x - y - borrow;
                if (diff < 0) {
                    diff += BASE;
                    borrow = 1;
                } else {
                    borrow = 0;
                }
                out[i] = (int) diff;
            }

            return out;
        }

        BigDec add(BigDec other) {
            Objects.requireNonNull(other, "other");

            if (sign == 0) return other;
            if (other.sign == 0) return this;

            if (sign == other.sign) {
                return new BigDec(
                        sign, addAbs(limbs, other.limbs));
            }

            int cmp = compareAbs(limbs, other.limbs);

            if (cmp == 0) return ZERO;

            if (cmp > 0) {
                return new BigDec(
                        sign,
                        subtractAbs(limbs, other.limbs));
            }

            return new BigDec(
                    other.sign,
                    subtractAbs(other.limbs, limbs));
        }

        BigDec subtract(BigDec other) {
            Objects.requireNonNull(other, "other");
            return add(other.negate());
        }

        BigDec multiply(BigDec other) {
            Objects.requireNonNull(other, "other");

            if (sign == 0 || other.sign == 0) {
                return ZERO;
            }

            int[] out =
                    new int[limbs.length + other.limbs.length];

            for (int i = 0; i < limbs.length; i++) {
                long carry = 0;

                for (int j = 0; j < other.limbs.length; j++) {
                    int at = i + j;
                    long cur = (long) out[at]
                            + (long) limbs[i] * other.limbs[j]
                            + carry;

                    out[at] = (int) (cur % BASE);
                    carry = cur / BASE;
                }

                int pos = i + other.limbs.length;
                while (carry != 0) {
                    long cur = (long) out[pos] + carry;
                    out[pos] = (int) (cur % BASE);
                    carry = cur / BASE;
                    pos++;
                }
            }

            return new BigDec(sign * other.sign, out);
        }

        // Division truncates toward zero, as BigInteger does.
        // The divisor is a positive int.
        DivRem divideByPositiveInt(int divisor) {
            if (divisor <= 0) {
                throw new IllegalArgumentException(
                        "Divisor must be positive");
            }

            int[] quotient = new int[limbs.length];
            long rem = 0;

            for (int i = limbs.length - 1; i >= 0; i--) {
                long cur = rem * BASE + limbs[i];
                quotient[i] = (int) (cur / divisor);
                rem = cur % divisor;
            }

            long signedRem = sign < 0 ? -rem : rem;
            return new DivRem(
                    new BigDec(sign, quotient),
                    signedRem);
        }
    }

    static void check(
            BigDec actual, BigInteger expected) {
        if (!new BigInteger(actual.toString())
                .equals(expected)) {
            throw new AssertionError(
                    "BigDec differs from BigInteger");
        }
    }

    public static void main(String[] args) {
        String aText =
                "1234567890123456789012345678901234567890";
        String bText =
                "987654321098765432109876543210";

        BigDec a = BigDec.parse(aText);
        BigDec b = BigDec.parse(bText);

        BigInteger refA = new BigInteger(aText);
        BigInteger refB = new BigInteger(bText);

        check(a.add(b), refA.add(refB));
        check(a.subtract(b), refA.subtract(refB));
        check(a.multiply(b), refA.multiply(refB));

        DivRem d = a.divideByPositiveInt(97);
        BigInteger[] checkDivision = refA.divideAndRemainder(
                BigInteger.valueOf(97));
        check(d.quotient(), checkDivision[0]);
        if (d.remainder() != checkDivision[1].longValueExact()) {
            throw new AssertionError("Wrong remainder");
        }

        System.out.println("a: " + a);
        System.out.println("b: " + b);
        System.out.println("a+b: " + a.add(b));
        System.out.println("a-b: " + a.subtract(b));
        System.out.println("b-a: " + b.subtract(a));
        System.out.println("a*b: " + a.multiply(b));
        System.out.println("a / 97: quotient="
                + d.quotient() + ", remainder=" + d.remainder());

        DivRem neg = a.negate().divideByPositiveInt(97);
        System.out.println("(-a) / 97: quotient="
                + neg.quotient()
                + ", remainder=" + neg.remainder());

        System.out.println("canonical -0000: "
                + BigDec.parse("-000000"));
        System.out.println("leading +00012300456: "
                + BigDec.parse("+00012300456"));
        System.out.println("signed addition: "
                + BigDec.parse("-12345678901234567890")
                        .add(BigDec.parse("987654321")));
        System.out.println("signed product: "
                + BigDec.parse("-12345678901234567890")
                        .multiply(BigDec.parse("987654321")));
        System.out.println("a compare b: "
                + a.compareTo(b));

        BigInteger max = BigInteger.valueOf(Long.MAX_VALUE);
        System.out.println("long max + 1: "
                + max.add(BigInteger.ONE));
        System.out.println("2^100: "
                + BigInteger.TWO.pow(100));
        System.out.println("2^1000 mod 1000000007: "
                + BigInteger.TWO.modPow(
                        BigInteger.valueOf(1000),
                        BigInteger.valueOf(1000000007L)));
        System.out.println("gcd(48,18): "
                + BigInteger.valueOf(48).gcd(
                        BigInteger.valueOf(18)));

        BigInteger negative = BigInteger.valueOf(-14);
        BigInteger five = BigInteger.valueOf(5);
        System.out.println("(-14) remainder 5: "
                + negative.remainder(five));
        System.out.println("(-14) mod 5: "
                + negative.mod(five));

        System.out.println("2^128 bitLength: "
                + BigInteger.ONE.shiftLeft(128).bitLength());

        BigInteger unsigned64 =
                new BigInteger("18446744073709551615");
        System.out.println("uint64 max hex: "
                + unsigned64.toString(16));
        System.out.println("byte sign round-trip: "
                + unsigned64.equals(
                        new BigInteger(unsigned64.toByteArray())));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 HugeIntegerRepresentationDemo.java
java HugeIntegerRepresentationDemo
~~~

**Đầu ra chính xác của ví dụ:**

~~~text
a: 1234567890123456789012345678901234567890
b: 987654321098765432109876543210
a+b: 1234567891111111110111111111011111111100
a-b: 1234567889135802467913580246791358024680
b-a: -1234567889135802467913580246791358024680
a*b: 1219326311370217952261850327337448559633622923332237463801111263526900
a / 97: quotient=12727504021891307103220058545373552246, remainder=28
(-a) / 97: quotient=-12727504021891307103220058545373552246, remainder=-28
canonical -0000: 0
leading +00012300456: 12300456
signed addition: -12345678900246913569
signed product: -12193263112482853211126352690
a compare b: 1
long max + 1: 9223372036854775808
2^100: 1267650600228229401496703205376
2^1000 mod 1000000007: 688423210
gcd(48,18): 6
(-14) remainder 5: -4
(-14) mod 5: 1
2^128 bitLength: 129
uint64 max hex: ffffffffffffffff
byte sign round-trip: true
~~~

### Những chi tiết quan trọng trong mã

**BigDec bất biến:** các trường là final, constructor sao chép mảng. Không có hàm cho phép caller sửa mảng sau khi tạo số, nên phép cộng và nhân không làm thay đổi các toán hạng.

**ZERO:** chỉ có một biểu diễn zero chuẩn trong mỗi kết quả; parse("-000") trả ZERO, negate(ZERO) vẫn là ZERO.

**add/subtract:** xử lý dấu riêng; subtract gọi add với negate, giảm logic trùng lặp.

**multiply:** mỗi phép nhân limb được ép long trước; giá trị trung gian nhỏ hơn BASE² và trong giới hạn long.

**divideByPositiveInt:** đi từ limb cao xuống thấp, dùng rem long, trả remainder có dấu tương thích BigInteger.divideAndRemainder.

**toString:** limb cao nhất không padding, các limb còn lại phải có đủ 9 chữ số.

**check:** ba phép toán lớn và phép chia được so với BigInteger ngay trong main. Đây là kiểm tra minh họa, không thay thế property-based testing trên nhiều đầu vào.

**Object equality:** BigDec triển khai equals và hashCode nên có thể dùng theo giá trị trong collection, không cần dựa vào object identity.

### Phạm vi của demo

Chương trình **chưa triển khai chia một số BigDec cho một BigDec bất kỳ**. Nó chỉ chia cho **một số nguyên int dương**. Nếu bài yêu cầu chia cho số lớn, dùng BigInteger hoặc triển khai một thuật toán long division tổng quát có chuẩn hóa.

Chương trình cũng chưa triển khai Karatsuba/FFT, biểu diễn binary packed hay các thao tác bit tổng quát. Đây là ví dụ dễ kiểm tra để hiểu **nền tảng biểu diễn nhiều khối và số học có dấu**.

## 20. Độ phức tạp khi số có nhiều chữ số

Gọi L_A và L_B là số limb của hai số, BASE=10^9.

| Phép toán | Thời gian của bản schoolbook | Bộ nhớ kết quả/phụ |
| --- | --- | --- |
| Parse D chữ số thập phân | O(D) | O(ceil(D/9)) |
| Xuất chuỗi D chữ số | O(D) | O(D) ký tự đầu ra |
| So sánh | O(max(L_A,L_B)) trường hợp xấu | O(1) phụ |
| Cộng | O(max(L_A,L_B)) | O(max(L_A,L_B)) |
| Trừ | O(L_A) sau khi biết |A|≥|B| | O(L_A) |
| Nhân | O(L_A·L_B) | O(L_A+L_B) |
| Chia cho int dương | O(L_A) | O(L_A) |
| GCD, chia hai số lớn | Phụ thuộc thuật toán | Phụ thuộc kích thước/triển khai |

### Phân biệt word operations và bit complexity

Trong bảng, mỗi phép cộng/nhân limb được coi như O(1) trên kiểu long an toàn. Đây là mô hình **word-RAM** cho số khối kích thước cố định.

Khi phân tích tối ưu thuật toán số lớn rất dài, phải xét chi phí nhân, chia và truy cập bộ nhớ chi tiết hơn; không nên tuyên bố BigInteger có cộng/nhân O(1).

### Vì sao nhân schoolbook có bộ nhớ O(L_A+L_B)?

Mảng chứa tích của hai số có tối đa L_A+L_B limb (tích của số có L_A và L_B limb không vượt BASE^(L_A+L_B) về độ lớn). Vòng lặp chỉ dùng một số biến carry và cur.

### Những thuật toán nhân nhanh hơn

Karatsuba giảm độ phức tạp từ O(L²) xuống khoảng **O(L^1.585)** cho số cân đối đủ lớn. Toom–Cook và các phương pháp dùng biến đổi (FFT/NTT hoặc thuật toán nhân số lớn khác) có thể nhanh hơn nữa ở kích thước rất lớn.

Ngưỡng chuyển thuật toán tùy môi trường, kích thước operand, memory và thư viện. Không nên tự dự đoán ngưỡng cụ thể của mọi phiên bản JDK.

## 21. Chia cho số lớn, Euclid và lũy thừa lớn

### Chia hai số rất lớn

Chia BigDec cho một BigDec bất kỳ đòi:

- So sánh độ lớn.
- Tìm thương từng chữ số/limb hoặc dùng phép ước lượng.
- Trừ bội phù hợp của số chia.
- Quản lý borrow, chuẩn hóa và dấu.
- Đảm bảo **A=B·Q+R** và quy ước về |R|<|B|.

Một thuật toán chia dài tổng quát thường phức tạp hơn cộng/trừ/nhân schoolbook; nên học rõ quy tắc dấu và chuẩn hóa trước khi cài.

Java BigInteger cung cấp **divide, remainder, divideAndRemainder** đã kiểm thử tốt. Khi không bắt buộc tự triển khai, đây là lựa chọn an toàn hơn.

### Euclid trên BigInteger

Ước chung lớn nhất có thể tính với:

**gcd(a,b)=gcd(b,a mod b)**,

lặp đến khi b=0.

Ví dụ:

~~~text
gcd(48,18)
= gcd(18,12)
= gcd(12,6)
= gcd(6,0)
= 6
~~~

BigInteger.gcd() trả gcd không âm và hỗ trợ các số vượt long.

### Lũy thừa nhanh và modulo

Đối với a^n chính xác, BigInteger.pow(int) có thể dùng khi n là int không âm.

Đối với a^n mod m, **BigInteger.modPow(exponent,modulus)** tính phần dư mà không phải tạo số a^n khổng lồ.

Ví dụ:

**2^1000 mod 1000000007 = 688423210**.

Khi số mũ là BigInteger cực lớn, modPow tiện hơn phép nâng lũy thừa nguyên toàn phần.

### Số mũ âm

Nếu tính a^(-n) như số hữu tỉ, kết quả thường không phải số nguyên. Với modulo dương, số mũ âm chỉ có ý nghĩa khi a có nghịch đảo modular. Không tự ý biến số mũ âm thành số dương mà bỏ điều kiện tồn tại nghịch đảo.

## 22. Lưu trữ, truyền dữ liệu và rủi ro làm tròn

### Chuỗi thập phân là định dạng trao đổi phổ biến

Khi hai hệ thống dùng kiểu số khác nhau, truyền số nguyên rất lớn dưới dạng **String thập phân** giúp tránh việc một bên parse sang float/double và làm tròn.

Ví dụ trong một JSON API:

~~~json
{
  "hugeInteger": "9223372036854775808"
}
~~~

Với hệ thống trung gian không hỗ trợ arbitrary-precision integer nguyên gốc, đây là lựa chọn an toàn hơn so với:

~~~json
{
  "hugeInteger": 9223372036854775808
}
~~~

trong trường hợp consumer có thể đọc JSON number thành IEEE-754 double.

### Tách value và formatting

Nếu người dùng nhập "+0000123", kiểu BigInteger hoặc BigDec sẽ chuẩn hóa thành **123**. Nếu dữ liệu thực ra là mã định danh mà số 0 đầu có ý nghĩa, phải giữ cả **rawText**.

### Serialization của số âm

Nếu truyền byte:

- Định nghĩa rõ signed/unsigned.
- Định nghĩa rõ big-endian/little-endian.
- Xác định số byte cố định hay biến độ dài.
- Kiểm tra dấu, byte 0 đầu và canonical encoding.

Nếu gửi chuỗi thập phân:

- Quy định có cho phép dấu '+' không.
- Quy định số 0 đầu.
- Quy định số âm 0 có được chuẩn hóa không.
- Chặn đầu vào quá lớn nếu cần bảo vệ tài nguyên.

### Giới hạn tài nguyên

Một đầu vào 100 triệu chữ số có thể làm tiêu tốn RAM và CPU đáng kể, ngay cả khi thư viện có thể biểu diễn về mặt lý thuyết. Hệ thống thực tế nên đặt giới hạn độ dài đầu vào, kích thước output và thời gian tính phù hợp với yêu cầu dịch vụ.

## 23. Những lỗi phổ biến khi xử lý số nguyên rất lớn

1. **Đọc một số lớn bằng Long.parseLong** dù dữ liệu vượt long.
2. **Cộng/nhân long trước rồi mới chuyển sang BigInteger**, nên đã overflow.
3. **Dùng double cho số nguyên cần chính xác**, đánh mất bit thấp.
4. **Coi JSON number luôn được giữ nguyên từng chữ số** ở mọi ngôn ngữ consumer.
5. **Không phân biệt giá trị số với mã định danh có số 0 đầu**.
6. **Lưu limb theo little-endian nhưng in trực tiếp từ chỉ số 0**, đảo thứ tự khối.
7. **Không padding đủ 9 chữ số cho những limb thấp khi toString**, mất độ lớn.
8. **Cho phép limb≥BASE hoặc limb âm**, phá bất biến.
9. **Không trim limb 0 cao nhất**, tạo nhiều biểu diễn cho cùng số.
10. **Không chuẩn hóa -0 thành 0**, làm compare/equals sai.
11. **Không kiểm tra ký tự parse**, vô tình nhận chữ hoặc khoảng trắng.
12. **Dùng Integer.parseInt cho toàn bộ số lớn**, vượt phạm vi int.
13. **Nhân hai int rồi mới gán vào long**, overflow trước ép kiểu.
14. **Không truyền carry cuối khi cộng**, mất một limb.
15. **Không truyền borrow đúng khi trừ**, sai hàng cao.
16. **Gọi trừ trị tuyệt đối khi |A|<|B|**, kết quả không hợp lệ.
17. **Quên đổi dấu khi cộng hai số trái dấu và |B|>|A|**, trả kết quả sai dấu.
18. **Quên xử lý A+(-A)=0**, để lại âm 0.
19. **Đặt tích limb tại i+j+1 thay vì i+j**, nhân sai trọng số.
20. **Không cộng giá trị out[i+j] hiện có khi nhân**, làm mất đóng góp từ cặp khác.
21. **Quên lan carry sau vòng j**, mất phần cao của tích.
22. **Chia theo limb thấp tới cao**, sai phương pháp chia dài.
23. **Dùng int cho rem·BASE trong phép chia**, overflow.
24. **Quên điều kiện divisor>0 trong hàm chia cho int**, sai hợp đồng.
25. **Coi BigInteger.remainder và BigInteger.mod là cùng quy ước trên số âm**, trả dư sai.
26. **Dùng == để so hai BigInteger object**, so identity thay vì giá trị.
27. **Gọi add/multiply BigInteger nhưng bỏ kết quả**, quên immutable.
28. **Dùng longValue() khi số không vừa long nhưng không kiểm tra**, mất bit.
29. **Nhầm BigInteger với BigDecimal khi có phần thập phân**, làm mất scale.
30. **Dùng BigInteger.toByteArray như chuỗi byte unsigned không dấu**, sai sign bit.
31. **Mất một byte 0 đầu khi round-trip BigInteger**, dù giao thức yêu cầu fixed width.
32. **Cho rằng BigInteger không thể hết RAM**, bỏ qua giới hạn tài nguyên.
33. **Cho rằng phép nhân big integer luôn O(L)**, quên schoolbook O(L²).
34. **Tự viết thuật toán nhân/chi cho dữ liệu sản xuất mà không kiểm thử độc lập**, rủi ro carry/borrow và ca biên.
35. **Không kiểm tra input null, rỗng hoặc chỉ có dấu**, gây lỗi khó hiểu.
36. **Không dùng bất biến A=B·Q+R để kiểm tra phép chia**, dễ bỏ sót lỗi remainder.
37. **Dùng Math.abs(Long.MIN_VALUE)** mà không hiểu phép lấy trị tuyệt đối overflow trên long.
38. **Đếm byte theo số ký tự thập phân**, nhầm độ dài chuỗi với độ dài biểu diễn nhị phân.

## 24. Kiểm thử độc lập và property-based testing

Khi tự cài BigDec, cách QA tốt nhất là dùng **java.math.BigInteger** làm oracle vì hai triển khai dùng các cách biểu diễn khác nhau.

Với mỗi cặp chuỗi thập phân A,B ngẫu nhiên có dấu:

1. Parse bằng BigDec và bằng BigInteger.
2. Đối chiếu BigDec.toString() với BigInteger.toString() về giá trị, kể cả số 0 đầu.
3. Đối chiếu **compareTo**.
4. Đối chiếu **A+B**.
5. Đối chiếu **A−B**.
6. Đối chiếu **A·B**.
7. Chọn divisor int d>0 và đối chiếu **A/d**, **A%d** theo BigInteger.divideAndRemainder.
8. Xác minh **A=d·Q+R** và **|R|<d**.
9. Kiểm tra **A+(-A)=0**.
10. Kiểm tra **A·0=0**, **A·1=A**, **A−A=0**.
11. Kiểm tra **commutativity** của cộng và nhân.
12. Kiểm tra hai object cùng giá trị có **equals/hashCode** giống nhau, nhưng không cần cùng identity.

### Những họ test đặc biệt quan trọng

| Dữ liệu | Mục tiêu |
| --- | --- |
| "0", "-0", "+0000" | Zero chuẩn hóa |
| "1", "-1" | Dấu và đơn vị |
| "999999999", "1" | Carry qua ranh giới BASE |
| "1000000000", "1" | Borrow qua ranh giới BASE |
| "999999999999999999" | Nhân nhiều limb gần BASE |
| 40–100 chữ số khác độ dài | Cộng, trừ, nhân lệch độ dài |
| A và -A | Phép cộng cho 0 |
| A=B | Trừ cho 0 |
| A<B | Dấu phép trừ |
| A âm, d>0 | Thương và remainder có dấu |
| d=1, d gần Integer.MAX_VALUE | Biên phép chia nhỏ |
| số có nhiều limb 0 ở giữa | Đúng khi padding output |
| chuỗi chỉ "+" hoặc "-" | Parse phải từ chối |
| chuỗi có dấu cách/dấu phẩy | Parse phải từ chối |
| 2^1000 mod1000000007 | BigInteger.modPow |

### Oracle của multiplication

Đừng tự kiểm tra schoolbook bằng một hàm schoolbook khác dùng cùng công thức/cách carry, vì cả hai có thể cùng sai. BigInteger.multiply giúp phát hiện lỗi độc lập ở toàn bộ giá trị kết quả.

### Kiểm tra chia có dấu

Với A âm, phần dư BigInteger.remainder có thể âm. Vì vậy cần so cùng **quy tắc chia cắt về 0**, không dùng modulo dương làm oracle khi code đang triển khai remainder.

### Kiểm tra tính bất biến

Lưu bản chuỗi của A,B trước phép cộng/nhân/chia; thực hiện phép toán, rồi xác minh A,B không đổi. Nếu mảng limb bị chia sẻ và sửa trực tiếp, một lỗi aliasing có thể làm toán hạng bị thay đổi mà output đầu tiên vẫn có vẻ đúng.

## 25. Câu hỏi và bài tập tự luyện

**Câu 1.** Tại sao Long.MAX_VALUE+1 không lưu được trong long?  
**Đáp án:** Vượt giới hạn 64-bit có dấu; dùng BigInteger để giữ giá trị chính xác.

**Câu 2.** BASE=10^9; mảng [5,3] little-endian biểu diễn số nào?  
**Đáp án:** 3·10^9+5=3000000005.

**Câu 3.** Vì sao cần padding mỗi limb thấp đủ 9 chữ số khi xuất?  
**Đáp án:** Mỗi limb mang trọng số BASE^i; không padding sẽ làm mất các chữ số 0 nằm giữa các khối.

**Câu 4.** Cộng hai limb cần xử lý gì?  
**Đáp án:** Carry theo BASE, lấy kết quả mod BASE và chuyển carry sang limb cao hơn.

**Câu 5.** Trừ trị tuyệt đối khi A<B có an toàn không?  
**Đáp án:** Không; phải đổi hướng trừ và quyết định dấu kết quả.

**Câu 6.** Nhân schoolbook đặt tích a[i]·b[j] ở vị trí nào?  
**Đáp án:** Limb i+j, cộng với giá trị đang có và carry.

**Câu 7.** Với BASE=10^9, vì sao tích hai limb có thể tính bằng long?  
**Đáp án:** Tích nhỏ hơn 10^18, còn Long.MAX_VALUE xấp xỉ 9.22×10^18.

**Câu 8.** Chia dài phải duyệt limb từ phía nào?  
**Đáp án:** Từ limb cao nhất xuống thấp nhất để đưa remainder sang vị trí kế tiếp.

**Câu 9.** -100/7 theo chia cắt về 0 cho quotient và remainder nào?  
**Đáp án:** Q=-14, R=-2.

**Câu 10.** -100 mod7 chuẩn không âm bằng bao nhiêu?  
**Đáp án:** 5.

**Câu 11.** BigInteger có bất biến không?  
**Đáp án:** Có; add/multiply tạo giá trị mới, không sửa object cũ.

**Câu 12.** Vì sao new BigInteger(bytes) có thể trả số âm?  
**Đáp án:** Constructor mặc định diễn giải byte[] theo two's complement có dấu.

**Câu 13.** Muốn đọc unsigned magnitude từ byte[], dùng constructor nào?  
**Đáp án:** new BigInteger(1, bytes) với bytes chứa độ lớn big-endian.

**Câu 14.** BigInteger.toByteArray() có giữ độ rộng byte cố định của input không?  
**Đáp án:** Không; nó trả biểu diễn two's-complement theo độ dài cần thiết.

**Câu 15.** Phân biệt BigInteger với BigDecimal?  
**Đáp án:** BigInteger chỉ số nguyên; BigDecimal có unscaled value và scale để biểu diễn decimal.

**Câu 16.** Nếu đang tính 2^1000 mod1000000007, dùng API nào?  
**Đáp án:** BigInteger.modPow.

**Câu 17.** Tại sao không dùng Number JavaScript cho mọi ID 64-bit?  
**Đáp án:** IEEE-754 double không giữ chính xác tất cả số nguyên ngoài miền 53-bit significand.

**Câu 18.** A có 40 chữ số, vì sao không dùng Long.parseLong(A)?  
**Đáp án:** Long chỉ tới khoảng 19 chữ số dương; dùng BigInteger hoặc parse từng khối.

**Câu 19.** Với BigDec immutable, vì sao constructor phải sao chép int[]?  
**Đáp án:** Tránh caller giữ reference rồi sửa mảng và thay đổi giá trị object.

**Câu 20.** Nếu cần chia hai BigDec bất kỳ, hàm divideByPositiveInt đủ chưa?  
**Đáp án:** Chưa; nó chỉ hỗ trợ divisor int dương, cần long division tổng quát hoặc BigInteger.

## 26. Tổng kết và checklist ứng dụng

Khi bài toán yêu cầu **số nguyên vượt độ rộng máy**, hãy làm theo trình tự:

1. **Đọc đúng kiểu dữ liệu:** số nguyên chính xác, số thập phân có scale, hay chuỗi định danh?
2. Nếu Java cho dùng thư viện, ưu tiên **BigInteger** cho số nguyên rất lớn.
3. Chuyển sang BigInteger **trước khi cộng/nhân có thể overflow**.
4. Nếu phải tự cài, chọn cơ số limb với cận tích đủ an toàn trong kiểu trung gian (ví dụ BASE=10^9 với long).
5. Duy trì bất biến **dấu ∈{-1,0,+1}**, các limb thuộc [0,BASE−1], không có zero limb cao nhất.
6. Cộng từ limb thấp lên cao với carry; trừ với borrow và điều kiện trị tuyệt đối.
7. Nhân schoolbook theo vị trí i+j; không bỏ qua giá trị đang có và carry.
8. Chia cho int dương từ limb cao xuống thấp; kiểm tra **A=dQ+R**.
9. Quy định rõ quy tắc **remainder có dấu** và **mod không âm**.
10. Khi parse/serialize, nêu rõ cơ số, dấu, leading zeros, UTF-8/byte order và độ rộng dữ liệu.
11. Dùng **equals/compareTo**, không so giá trị hai object bằng ==.
12. Với số từ giao thức byte unsigned, tránh nhầm two's complement.
13. Phân tích complexity theo **số limb**, không giả định BigInteger arithmetic là O(1).
14. Đặt giới hạn tài nguyên phù hợp nếu đầu vào có thể cực lớn.
15. Kiểm thử với **BigInteger làm oracle** trên hàng trăm hoặc hàng nghìn số ngẫu nhiên và đủ ca biên.

**Kết luận:** số nguyên vượt độ rộng máy không phải một khái niệm huyền bí; nó là việc **thay một từ máy bằng nhiều khối**, thực hiện đúng quy tắc số học và duy trì chuẩn hóa. Hiểu biểu diễn theo limb giúp thấy được cách các thư viện BigInteger hoạt động, lựa chọn API an toàn và tránh các lỗi precision/overflow khó phát hiện.

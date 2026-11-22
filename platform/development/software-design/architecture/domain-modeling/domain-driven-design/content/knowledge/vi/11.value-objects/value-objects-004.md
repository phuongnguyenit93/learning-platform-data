# So sánh bằng giá trị và cài đặt equals, hashCode

Trong Domain-Driven Design (DDD), Value Object (đối tượng giá trị) được nhận diện bằng những giá trị cấu thành nó thay vì một danh tính riêng. Hai đối tượng biểu diễn cùng một giá trị nghiệp vụ được xem là bằng nhau, ngay cả khi chúng được tạo ở hai thời điểm khác nhau và nằm ở hai vị trí bộ nhớ khác nhau.

Trong Java, hành vi này được thể hiện chủ yếu qua hai phương thức equals() và hashCode(). Nếu cài đặt sai, Value Object có thể hoạt động không nhất quán khi so sánh, tìm kiếm trong HashSet, sử dụng làm khóa HashMap hoặc được xử lý trong các thuật toán loại bỏ trùng lặp.

Bài học này giải thích ý nghĩa của equality theo giá trị, hợp đồng của equals() và hashCode(), cách cài đặt chúng cho Value Object, những bẫy thường gặp với BigDecimal và Java record, cũng như cách kiểm thử để bảo đảm mô hình giữ được ngữ nghĩa nghiệp vụ.

## 1. Equality theo giá trị trong DDD

### 1.1. Hai Value Object bằng nhau khi biểu diễn cùng một giá trị

Giả sử một hệ thống bán hàng tạo hai đối tượng Money:

- Đối tượng thứ nhất biểu diễn 150.000 VND.
- Đối tượng thứ hai cũng biểu diễn 150.000 VND.

Nếu loại tiền và số tiền có cùng ý nghĩa nghiệp vụ, hai đối tượng này bằng nhau dù được tạo bằng hai câu lệnh new riêng biệt.

~~~java
Money first = new Money(
    new BigDecimal("150000"),
    Currency.getInstance("VND")
);

Money second = new Money(
    new BigDecimal("150000"),
    Currency.getInstance("VND")
);
~~~

Theo ngữ nghĩa Value Object:

~~~java
first.equals(second); // true
~~~

Điều này khác với phép so sánh tham chiếu:

~~~java
first == second; // false
~~~

Toán tử == trên hai biến kiểu tham chiếu kiểm tra chúng có trỏ đến cùng một đối tượng hay không. Phương thức equals() kiểm tra sự bằng nhau theo định nghĩa của kiểu đối tượng.

### 1.2. So sánh Entity và Value Object

Entity được nhận diện bằng danh tính ổn định. Hai Entity có cùng thuộc tính vẫn có thể là hai đối tượng khác nhau.

Value Object được nhận diện bằng giá trị. Nếu tất cả thuộc tính có ý nghĩa cấu thành giá trị đều tương đương, hai đối tượng được xem là bằng nhau.

| Tiêu chí | Entity | Value Object |
|---|---|---|
| Cách nhận diện | Danh tính riêng | Giá trị cấu thành |
| Equality | Thường dựa trên identity | Dựa trên value |
| Thay đổi | Có thể thay đổi trạng thái theo vòng đời | Thường bất biến |
| Ví dụ | Customer, Order, Account | Money, Address, Quantity, DateRange |
| Hai đối tượng cùng thuộc tính | Có thể vẫn khác nhau nếu ID khác | Thường bằng nhau nếu giá trị tương đương |

Ví dụ, hai khách hàng có cùng tên và địa chỉ không nhất thiết là một khách hàng. Họ có thể là hai người khác nhau. Nhưng hai Money cùng số tiền và loại tiền có thể được xem là cùng một giá trị.

### 1.3. Xác định những thuộc tính tham gia equality

Không phải mọi field đều mặc nhiên phải được đưa vào equals() và hashCode(). Chỉ những thuộc tính cấu thành ý nghĩa của Value Object mới nên tham gia.

Ví dụ Money có thể gồm:

- amount: số tiền.
- currency: loại tiền.

Nếu hai Money có cùng amount nhưng khác currency, chúng không bằng nhau.

~~~text
Money(100, USD) không bằng Money(100, VND)
Money(100, USD) bằng Money(100.00, USD)
~~~

Dòng thứ hai chỉ đúng nếu nghiệp vụ xem scale của số thập phân là không có ý nghĩa đối với equality. Nếu scale hoặc độ chính xác có ý nghĩa nghiệp vụ riêng, định nghĩa phải khác. Người thiết kế cần xác nhận semantics trước khi viết code.

Các thuộc tính như thời điểm tạo đối tượng, số lần đọc, bộ đếm cache hoặc thông tin log thường không phải thành phần của giá trị. Không đưa chúng vào equality nếu chúng không làm thay đổi ý nghĩa nghiệp vụ.

## 2. Vai trò của equals() và hashCode() trong Java

### 2.1. equals() xác định hai đối tượng có bằng nhau không

Mọi lớp Java đều kế thừa equals() từ Object. Cài đặt mặc định của Object.equals() kiểm tra identity: hai tham chiếu phải trỏ đến cùng đối tượng.

Value Object cần định nghĩa lại equals() để so sánh các thành phần giá trị.

~~~java
Money first = new Money(
    new BigDecimal("100"),
    Currency.getInstance("USD")
);

Money second = new Money(
    new BigDecimal("100"),
    Currency.getInstance("USD")
);

System.out.println(first.equals(second)); // true nếu Money định nghĩa equality theo giá trị
~~~

Nếu không override equals(), hai đối tượng được tạo riêng sẽ không được xem là bằng nhau dù nội dung giống hệt.

### 2.2. hashCode() cung cấp mã băm phục vụ cấu trúc dữ liệu

hashCode() trả về một số nguyên được dùng bởi các cấu trúc dữ liệu dựa trên hash, chẳng hạn:

- HashSet.
- HashMap.
- LinkedHashSet.
- LinkedHashMap.
- Một số thư viện cache hoặc indexing.

Hash không phải mã định danh duy nhất. Hai đối tượng khác nhau có thể có cùng hashCode(). Đây là hiện tượng collision và các collection vẫn cần gọi equals() để xác định phần tử có thực sự bằng nhau không.

Ví dụ:

Trong đoạn mã này, first và second là hai biến đã được tạo ở ví dụ trước.

~~~java
Set<Money> prices = new HashSet<>();

prices.add(first);
prices.add(second);

System.out.println(prices.size()); // 1 nếu first và second bằng nhau
~~~

HashSet sử dụng hashCode() để tìm vùng lưu trữ phù hợp, sau đó dùng equals() để kiểm tra phần tử đã tồn tại hay chưa.

### 2.3. Hợp đồng bắt buộc giữa equals() và hashCode()

Java quy định mối quan hệ quan trọng:

**Nếu hai đối tượng bằng nhau theo equals(), chúng bắt buộc phải có cùng hashCode().**

~~~text
a.equals(b) == true
        |
        v
a.hashCode() == b.hashCode()
~~~

Chiều ngược lại không bắt buộc. Hai đối tượng có cùng hashCode() chưa chắc bằng nhau.

~~~text
a.hashCode() == b.hashCode()
        |
        v
a.equals(b) có thể true hoặc false
~~~

Nếu equals() cho rằng hai đối tượng bằng nhau nhưng hashCode() khác nhau, HashSet có thể lưu cả hai và HashMap có thể không tìm được khóa tương đương. Điều đó phá vỡ ngữ nghĩa của collection.

### 2.4. Các thuộc tính của hợp đồng equals()

Một cài đặt equals() đúng phải tuân thủ các tính chất sau:

| Tính chất | Ý nghĩa | Ví dụ |
|---|---|---|
| Reflexive (phản xạ) | Đối tượng luôn bằng chính nó | a.equals(a) là true |
| Symmetric (đối xứng) | Nếu a bằng b thì b phải bằng a | a.equals(b) và b.equals(a) cùng true |
| Transitive (bắc cầu) | Nếu a bằng b và b bằng c thì a phải bằng c | Ba Money tương đương phải nhất quán |
| Consistent (nhất quán) | Khi dữ liệu tham gia equality không đổi, kết quả lặp lại không đổi | Gọi equals nhiều lần cho cùng cặp cho cùng kết quả |
| Non-null | Đối tượng khác null không bằng null | a.equals(null) là false |

Ngoài ra, hashCode() phải trả về cùng kết quả trong các lần gọi khi thông tin được dùng trong equality không thay đổi. Các đối tượng bằng nhau phải có cùng hashCode().

## 3. Thiết kế equality trước khi viết code

### 3.1. Xác định ngữ nghĩa giá trị

Trước tiên, hãy trả lời:

- Đối tượng này đại diện cho giá trị nghiệp vụ nào?
- Thuộc tính nào tạo nên giá trị?
- Có thuộc tính nào chỉ phục vụ kỹ thuật hoặc hiển thị?
- Có cần chuẩn hóa dữ liệu trước khi so sánh không?
- Hai biểu diễn khác nhau về mặt cú pháp có thể cùng một giá trị không?

Ví dụ, một địa chỉ có thể chứa tên đường, thành phố, mã bưu chính và quốc gia. Có nên xem chữ hoa và chữ thường là tương đương không? Có nên loại bỏ khoảng trắng đầu cuối không? Việc này phụ thuộc quy tắc nghiệp vụ và dữ liệu nguồn.

Không tự ý chuẩn hóa dữ liệu chỉ để equals() dễ cài đặt. Chuẩn hóa sai có thể làm mất thông tin hoặc gộp hai giá trị mà nghiệp vụ phân biệt.

### 3.2. Tách giá trị khỏi metadata

Giả sử một Money có thêm trường createdAt để phục vụ theo dõi thời điểm khởi tạo. Nếu createdAt không làm thay đổi giá trị tiền, nó không nên tham gia equals() và hashCode().

Ngược lại, currency là phần thiết yếu của Money. Nếu bỏ currency khỏi equality, 100 USD có thể bị xem là bằng 100 VND, điều này sai về mặt nghiệp vụ.

### 3.3. Equality nên cùng kiểu khái niệm

Không nên xem Money(100, USD) bằng BigDecimal(100) chỉ vì amount giống nhau. Một giá trị tiền bao gồm cả đơn vị tiền tệ và quy tắc nghiệp vụ.

Tương tự, Quantity(5, BOX) không nhất thiết bằng Quantity(5, PIECE). Hai giá trị có cùng con số nhưng khác đơn vị đo.

### 3.4. Value Object nên bất biến

Nếu thuộc tính tham gia equality thay đổi sau khi đối tượng được thêm vào HashSet hoặc dùng làm khóa HashMap, hashCode() có thể thay đổi. Collection có thể không tìm được đối tượng ở vị trí cũ.

Do đó, Value Object nên:

- Dùng field final.
- Không cung cấp setter.
- Không để lộ collection có thể sửa.
- Sao chép dữ liệu mutable khi nhận vào và khi trả ra.
- Chỉ cung cấp hành vi tạo ra một Value Object mới khi giá trị thay đổi.

Bất biến giúp equality và hashCode ổn định trong suốt vòng đời của đối tượng.

## 4. Cài đặt equals() và hashCode() cho Value Object

### 4.1. Ví dụ Money bất biến

Giả sử nghiệp vụ quy định scale của số thập phân không làm thay đổi giá trị tiền. Khi đó 10.0 USD và 10.00 USD được xem là bằng nhau.

Ta có thể chuẩn hóa BigDecimal trong constructor bằng stripTrailingZeros(), sau đó dùng equals() và hashCode() trên giá trị đã chuẩn hóa.

Các ví dụ Java trong bài lược bỏ những import chuẩn như java.math.BigDecimal, java.util.Objects, java.util.Currency và các kiểu collection để tập trung vào phần mô hình. Đoạn kiểm thử sử dụng cú pháp JUnit 5.

~~~java
public final class Money {

    private final BigDecimal amount;
    private final Currency currency;

    public Money(BigDecimal amount, Currency currency) {
        this.amount = Objects.requireNonNull(amount)
            .stripTrailingZeros();

        this.currency = Objects.requireNonNull(currency);
    }

    public BigDecimal amount() {
        return amount;
    }

    public Currency currency() {
        return currency;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }

        if (!(other instanceof Money money)) {
            return false;
        }

        return amount.equals(money.amount)
            && currency.equals(money.currency);
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount, currency);
    }
}
~~~

Lớp Money là final nên không có lớp con thay đổi cách so sánh. Constructor chuẩn hóa amount trước khi lưu. Vì vậy:

~~~java
Money a = new Money(
    new BigDecimal("10.0"),
    Currency.getInstance("USD")
);

Money b = new Money(
    new BigDecimal("10.00"),
    Currency.getInstance("USD")
);

System.out.println(a.equals(b)); // true
System.out.println(a.hashCode() == b.hashCode()); // true
~~~

Nếu nghiệp vụ xem scale là một phần của giá trị, không dùng stripTrailingZeros(). Hãy giữ nguyên scale và dùng semantics phù hợp.

### 4.2. Vì sao dùng Objects.requireNonNull()

Một Value Object thường không có ý nghĩa nếu thiếu thành phần bắt buộc. Money không thể có amount hoặc currency null.

Kiểm tra null ngay trong constructor giúp đối tượng không bao giờ được tạo ở trạng thái thiếu thành phần. equals() và hashCode() vì vậy không cần xử lý những trạng thái không hợp lệ này ở mọi nơi.

Nếu một thuộc tính thực sự là tùy chọn theo nghiệp vụ, hãy mô hình hóa điều đó rõ ràng và dùng Objects.equals() hoặc logic phù hợp để so sánh null.

### 4.3. Vì sao dùng Objects.hash()

Objects.hash(amount, currency) tạo hash dựa trên các thành phần. Cách này ngắn gọn và dễ đọc, phù hợp với nhiều Value Object.

Có thể tự tính hash để tránh tạo mảng varargs:

~~~java
@Override
public int hashCode() {
    int result = amount.hashCode();
    result = 31 * result + currency.hashCode();
    return result;
}
~~~

Hai cách đều hợp lệ nếu sử dụng cùng chính xác các thành phần equality và bảo đảm hợp đồng. Không nên tối ưu sớm bằng một thuật toán hash khó hiểu. Chỉ cân nhắc khi profiling cho thấy hashCode() là điểm nóng thực sự.

### 4.4. Sử dụng Objects.equals() khi có trường tùy chọn

Nếu Value Object có trường có thể null, có thể dùng:

~~~java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }

    if (!(other instanceof DeliveryWindow window)) {
        return false;
    }

    return Objects.equals(start, window.start)
        && Objects.equals(end, window.end)
        && Objects.equals(timeZone, window.timeZone);
}
~~~

Objects.equals(a, b) trả về true nếu cả hai cùng null hoặc nếu a.equals(b) trả về true. Nó giúp tránh NullPointerException khi so sánh thành phần tùy chọn.

Tuy nhiên, nếu start hoặc end bắt buộc phải có, hãy kiểm tra trong constructor. Đừng dùng null như một cách né tránh việc xác định mô hình miền.

## 5. Bẫy BigDecimal: equals() và compareTo()

### 5.1. BigDecimal phân biệt scale trong equals()

BigDecimal có hai khái niệm so sánh dễ gây nhầm:

~~~java
BigDecimal x = new BigDecimal("10.0");
BigDecimal y = new BigDecimal("10.00");

System.out.println(x.equals(y));    // false
System.out.println(x.compareTo(y)); // 0
~~~

equals() xem cả giá trị và scale. compareTo() so sánh giá trị số và trả về 0 khi hai số có giá trị bằng nhau dù scale khác nhau.

Vì vậy, nếu Value Object dùng BigDecimal trực tiếp trong equals(), kết quả có thể không khớp với ngữ nghĩa nghiệp vụ.

### 5.2. Có ba cách xử lý thường gặp

| Cách | Khi phù hợp | Lưu ý |
|---|---|---|
| Chuẩn hóa bằng stripTrailingZeros() | Scale không có ý nghĩa đối với equality | Cần thống nhất cách lưu và hiển thị |
| Dùng compareTo() trong equals() và chuẩn hóa trong hashCode() | Muốn giữ biểu diễn gốc nhưng so sánh theo giá trị số | Phải bảo đảm hash dùng cùng semantics |
| Giữ nguyên scale | Scale là một phần của giá trị nghiệp vụ | 10.0 và 10.00 được xem là khác |

Cách thứ nhất thường đơn giản khi mô hình muốn canonicalize giá trị ngay khi tạo.

### 5.3. Nếu dùng compareTo(), hashCode() phải tương ứng

Một cài đặt sai thường gặp:

~~~java
@Override
public boolean equals(Object other) {
    if (!(other instanceof Price price)) {
        return false;
    }

    return amount.compareTo(price.amount) == 0;
}

@Override
public int hashCode() {
    return amount.hashCode();
}
~~~

Với 10.0 và 10.00, equals() trả về true nhưng BigDecimal.hashCode() có thể khác nhau do scale. Cài đặt này vi phạm hợp đồng.

Nếu muốn so sánh số học không phụ thuộc scale, có thể chuẩn hóa trong hash:

~~~java
@Override
public int hashCode() {
    return amount.stripTrailingZeros().hashCode();
}
~~~

Vẫn cần đưa các thuộc tính khác như currency vào hash nếu chúng tham gia equals().

### 5.4. Phân biệt equality với làm tròn tiền tệ

stripTrailingZeros() chỉ chuẩn hóa cách biểu diễn số, không phải quy tắc làm tròn tiền tệ.

Ví dụ, 10.005 USD có được làm tròn thành 10.01 USD hay không là một quy tắc nghiệp vụ riêng, phụ thuộc loại giao dịch và chính sách làm tròn. Không được dùng stripTrailingZeros() để thay thế rounding mode hoặc scale quy định cho tiền tệ.

Nếu cần làm tròn, hãy có hành vi hoặc chính sách rõ ràng, chẳng hạn roundForSettlement() hoặc một dịch vụ miền chịu trách nhiệm tính toán.

## 6. Sử dụng Java record cho Value Object

### 6.1. Record tự sinh equals() và hashCode()

Từ Java 16, record là lựa chọn phù hợp cho nhiều Value Object đơn giản. Java tự sinh constructor, accessor, equals(), hashCode() và toString() dựa trên các component.

~~~java
public record Address(
    String street,
    String city,
    String postalCode,
    String countryCode
) {
    public Address {
        street = Objects.requireNonNull(street).trim();
        city = Objects.requireNonNull(city).trim();
        postalCode = Objects.requireNonNull(postalCode).trim();
        countryCode = Objects.requireNonNull(countryCode).trim()
            .toUpperCase(Locale.ROOT);
    }
}
~~~

Hai Address có cùng các component sau chuẩn hóa sẽ bằng nhau theo equals() được sinh tự động.

~~~java
Address a = new Address(
    "12 Nguyen Hue",
    "Ho Chi Minh City",
    "700000",
    "vn"
);

Address b = new Address(
    "12 Nguyen Hue",
    "Ho Chi Minh City",
    "700000",
    "VN"
);

System.out.println(a.equals(b)); // true
~~~

Chuẩn hóa countryCode thành chữ hoa là một quyết định trong ví dụ. Chỉ thực hiện chuẩn hóa tương tự khi quy tắc miền xác nhận hai cách viết là cùng một giá trị.

### 6.2. Record chỉ bất biến nông (shallow immutability)

Các component của record là final, nhưng nếu component trỏ đến một đối tượng mutable thì đối tượng đó vẫn có thể thay đổi.

Ví dụ:

~~~java
public record Tags(List<String> values) {
}
~~~

Nếu truyền một ArrayList vào, bên gọi vẫn có thể sửa danh sách sau khi tạo Tags. Điều đó có thể làm thay đổi equality và hashCode của record.

Hãy sao chép và đóng băng collection:

~~~java
public record Tags(List<String> values) {
    public Tags {
        values = List.copyOf(values);
    }
}
~~~

Với mảng, cần sao chép cả đầu vào và đầu ra, đồng thời tự định nghĩa equality theo nội dung mảng nếu đó là ngữ nghĩa mong muốn.

### 6.3. Bẫy mảng trong record

Mảng Java không so sánh nội dung bằng equals() mặc định. Hai mảng có cùng byte vẫn không bằng nhau nếu là hai instance khác nhau.

~~~java
byte[] first = {1, 2, 3};
byte[] second = {1, 2, 3};

System.out.println(first.equals(second)); // false
System.out.println(Arrays.equals(first, second)); // true
~~~

Nếu record chứa byte[] và dùng equals() tự sinh, record sẽ dùng semantics equals() của mảng, tức là so sánh identity của mảng.

Một Value Object chứa mảng cần tự bảo vệ tính bất biến và định nghĩa equality theo nội dung:

~~~java
public final class Digest {

    private final byte[] bytes;

    public Digest(byte[] bytes) {
        this.bytes = Objects.requireNonNull(bytes).clone();
    }

    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }

        if (!(other instanceof Digest digest)) {
            return false;
        }

        return Arrays.equals(bytes, digest.bytes);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }
}
~~~

Nếu dùng record cho dữ liệu dạng mảng, cần override accessor để trả bản sao và override equals/hashCode để so sánh nội dung. Đừng giả định record tự động làm mọi component trở nên bất biến sâu.

## 7. Những lỗi thường gặp khi cài đặt equals() và hashCode()

### 7.1. Override equals() nhưng quên hashCode()

Đây là lỗi phổ biến nhất. Hai đối tượng có thể bằng nhau theo equals() nhưng hash khác nhau. HashSet và HashMap sẽ hoạt động không như mong đợi.

Luôn xem equals() và hashCode() là một cặp. Khi thay đổi thuộc tính tham gia equality, hãy xem lại cả hai phương thức.

### 7.2. Dùng == để so sánh object

~~~java
return this.currency == money.currency;
~~~

Với object như Currency, String hoặc Value Object khác, nên dùng equals() thay vì ==, trừ khi đang so sánh enum hoặc cố ý kiểm tra identity.

### 7.3. Bỏ sót một thuộc tính cấu thành giá trị

Nếu Money chỉ so sánh amount mà bỏ currency, 100 USD sẽ bằng 100 VND. Nếu Address bỏ countryCode, hai địa chỉ ở hai quốc gia có thể bị xem là bằng nhau.

Hãy xác định đầy đủ các thuộc tính cấu thành giá trị trước khi viết code.

### 7.4. Đưa thuộc tính kỹ thuật vào equality

Một trường createdAt, cacheKey hoặc displayLabel không nhất thiết thuộc giá trị nghiệp vụ. Nếu đưa nó vào equality, hai giá trị giống nhau có thể bị xem là khác chỉ vì thời điểm tạo hoặc cách hiển thị.

### 7.5. Dùng field mutable trong hashCode()

Nếu hashCode phụ thuộc vào danh sách mutable hoặc field có thể đổi, đối tượng có thể nằm sai bucket sau khi bị thay đổi.

Value Object nên bất biến. Nếu bắt buộc dùng dữ liệu mutable, không sử dụng đối tượng đó làm khóa trong hash collection trong khi dữ liệu có thể thay đổi.

### 7.6. Dùng instanceof với hệ thống kế thừa không được kiểm soát

Equality phải đối xứng. Nếu lớp cha và lớp con so sánh theo các tập thuộc tính khác nhau, có thể xảy ra trường hợp a.equals(b) là true nhưng b.equals(a) là false.

Với Value Object, thường nên dùng lớp final hoặc record để tránh kế thừa. Nếu cần hierarchy, phải thiết kế semantics equality rõ ràng và kiểm tra tính đối xứng, bắc cầu.

### 7.7. Dùng hashCode như mã định danh

HashCode không bảo đảm duy nhất, có thể thay đổi khi thuật toán hoặc dữ liệu thay đổi và không được thiết kế để lưu lâu dài. Không dùng nó thay cho ID, khóa nghiệp vụ hoặc checksum.

### 7.8. Dùng Objects.hash() mà không hiểu collision

Objects.hash() không tạo hash duy nhất. Collision là bình thường và collection xử lý bằng equals(). Không nên viết logic nghiệp vụ dựa trên việc hai hash khác nhau hoặc giống nhau.

### 7.9. Nhầm compareTo() với equals()

Comparable.compareTo() xác định thứ tự. equals() xác định equality. Với BigDecimal, hai phương thức có semantics khác nhau về scale. Nếu Value Object triển khai Comparable, cần cân nhắc để compareTo() nhất quán với equals(), đặc biệt khi dùng TreeSet hoặc TreeMap.

## 8. Tác động của equality đến Collection

### 8.1. HashSet loại bỏ phần tử trùng theo equals/hashCode

~~~java
Set<Money> values = new HashSet<>();

values.add(new Money(
    new BigDecimal("25.0"),
    Currency.getInstance("USD")
));

values.add(new Money(
    new BigDecimal("25.00"),
    Currency.getInstance("USD")
));

System.out.println(values.size()); // 1 nếu Money chuẩn hóa scale
~~~

Nếu hashCode() không phù hợp với equals(), HashSet có thể giữ cả hai đối tượng.

### 8.2. HashMap sử dụng Value Object làm khóa

~~~java
Map<Money, String> labels = new HashMap<>();

Money key = new Money(
    new BigDecimal("50.00"),
    Currency.getInstance("USD")
);

labels.put(key, "Fifty dollars");

Money lookup = new Money(
    new BigDecimal("50.0"),
    Currency.getInstance("USD")
);

System.out.println(labels.get(lookup)); // Fifty dollars
~~~

Khả năng tra cứu bằng một instance khác có cùng giá trị là một lợi ích quan trọng của Value Object.

### 8.3. TreeSet và TreeMap dùng thứ tự so sánh

TreeSet và TreeMap dựa vào compareTo() hoặc Comparator để xác định vị trí và tính tương đương trong cây. Nếu compareTo() trả về 0 cho hai đối tượng mà equals() trả về false, TreeSet có thể xem chúng là cùng một phần tử dù HashSet xem chúng là khác nhau.

Vì vậy, khi Value Object triển khai Comparable, nên bảo đảm thứ tự so sánh phù hợp với equality nếu muốn dùng an toàn trong cả hai nhóm collection.

### 8.4. Không thay đổi đối tượng sau khi dùng làm khóa

~~~java
Set<MutableKey> keys = new HashSet<>();
MutableKey key = new MutableKey("A");

keys.add(key);
key.setValue("B");

// contains(key) có thể không tìm được theo bucket cũ
~~~

Đây là một minh họa về rủi ro của khóa mutable. Với Value Object bất biến, tình huống này được loại bỏ từ thiết kế.

## 9. Kiểm thử equals() và hashCode()

### 9.1. Kiểm tra bằng nhau theo giá trị

~~~java
@Test
void moneyWithSameValueShouldBeEqual() {
    Money first = new Money(
        new BigDecimal("10.0"),
        Currency.getInstance("USD")
    );

    Money second = new Money(
        new BigDecimal("10.00"),
        Currency.getInstance("USD")
    );

    assertEquals(first, second);
}
~~~

### 9.2. Kiểm tra hợp đồng hashCode()

~~~java
@Test
void equalMoneyShouldHaveSameHashCode() {
    Money first = new Money(
        new BigDecimal("10.0"),
        Currency.getInstance("USD")
    );

    Money second = new Money(
        new BigDecimal("10.00"),
        Currency.getInstance("USD")
    );

    assertEquals(first, second);
    assertEquals(first.hashCode(), second.hashCode());
}
~~~

### 9.3. Kiểm tra thuộc tính khác nhau

~~~java
@Test
void differentCurrencyShouldNotBeEqual() {
    Money usd = new Money(
        new BigDecimal("10"),
        Currency.getInstance("USD")
    );

    Money vnd = new Money(
        new BigDecimal("10"),
        Currency.getInstance("VND")
    );

    assertNotEquals(usd, vnd);
}
~~~

### 9.4. Kiểm tra HashSet và HashMap

~~~java
@Test
void equalMoneyShouldBeOneElementInHashSet() {
    Set<Money> values = new HashSet<>();

    values.add(new Money(
        new BigDecimal("10.0"),
        Currency.getInstance("USD")
    ));

    values.add(new Money(
        new BigDecimal("10.00"),
        Currency.getInstance("USD")
    ));

    assertEquals(1, values.size());
}
~~~

~~~java
@Test
void equivalentMoneyShouldFindHashMapEntry() {
    Map<Money, String> values = new HashMap<>();

    values.put(
        new Money(
            new BigDecimal("10.0"),
            Currency.getInstance("USD")
        ),
        "ten"
    );

    Money lookup = new Money(
        new BigDecimal("10.00"),
        Currency.getInstance("USD")
    );

    assertEquals("ten", values.get(lookup));
}
~~~

### 9.5. Kiểm tra các tính chất equals()

Nên kiểm tra reflexive, symmetric, transitive, consistent và non-null. Có thể viết test riêng hoặc sử dụng thư viện kiểm tra hợp đồng equality nếu dự án đã có.

Ví dụ:

~~~java
@Test
void equalsShouldBeSymmetricAndTransitive() {
    Money a = new Money(
        new BigDecimal("10.0"),
        Currency.getInstance("USD")
    );

    Money b = new Money(
        new BigDecimal("10.00"),
        Currency.getInstance("USD")
    );

    Money c = new Money(
        new BigDecimal("10.000"),
        Currency.getInstance("USD")
    );

    assertEquals(a, a);
    assertEquals(a, b);
    assertEquals(b, a);
    assertEquals(b, c);
    assertEquals(a, c);
    assertNotEquals(a, null);
}
~~~

Bài kiểm thử này minh họa các trường hợp cơ bản. Một bộ kiểm tra đầy đủ nên dùng nhiều giá trị và kiểu đối tượng khác nhau, bao gồm trường hợp collision hash nếu cần.

## 10. Equality và ngôn ngữ chung trong miền

### 10.1. Equality là quyết định nghiệp vụ

Việc hai đối tượng có bằng nhau hay không không chỉ là chi tiết Java. Đó là một phần định nghĩa Value Object.

Ví dụ, hai địa chỉ có cùng số nhà và tên đường nhưng khác mã bưu chính có thể là hai địa chỉ khác nhau. Hai khoảng thời gian có cùng thời điểm bắt đầu nhưng khác thời điểm kết thúc chắc chắn không biểu diễn cùng một khoảng.

Một email có phân biệt chữ hoa chữ thường hay không phụ thuộc vào quy tắc định danh và hệ thống nhận email. Không nên tự chuyển mọi email về chữ thường nếu miền không cho phép.

### 10.2. Chuẩn hóa cần có chủ sở hữu

Nếu nhiều hệ thống tự chuẩn hóa cùng một dữ liệu theo các quy tắc khác nhau, equality giữa chúng có thể không thống nhất.

Hãy xác định:

- Ngữ cảnh nào sở hữu định nghĩa giá trị?
- Quy tắc chuẩn hóa nào được áp dụng?
- Chuẩn hóa xảy ra khi nhập, khi tạo Value Object hay khi hiển thị?
- Có cần giữ nguyên biểu diễn gốc để đối soát không?

Không phải mọi biểu diễn khác nhau đều cần bị hợp nhất. Một số trường hợp cần giữ nguyên dữ liệu đầu vào để kiểm toán hoặc đáp ứng yêu cầu pháp lý.

### 10.3. Equality giúp mô hình diễn đạt khái niệm rõ hơn

Khi Value Object có equality chính xác, code nghiệp vụ trở nên dễ đọc:

~~~java
if (requestedAddress.equals(customer.deliveryAddress())) {
    // Cùng một giá trị địa chỉ giao hàng theo định nghĩa của miền
}
~~~

Bên gọi không cần tự so sánh từng thuộc tính ở mọi nơi. Quy tắc equality được định nghĩa một lần trong Value Object và tái sử dụng nhất quán.

## 11. Checklist thiết kế equals() và hashCode()

Trước khi hoàn thành một Value Object, hãy kiểm tra:

- Đã xác định rõ ý nghĩa nghiệp vụ của giá trị.
- Đã chọn đầy đủ các thuộc tính tham gia equality.
- Đã loại bỏ metadata không thuộc giá trị.
- Đã xác định cách chuẩn hóa và so sánh dữ liệu.
- equals() tuân thủ reflexive, symmetric, transitive, consistent và non-null.
- Hai đối tượng bằng nhau luôn có cùng hashCode().
- hashCode() sử dụng cùng các thành phần và semantics với equals().
- Đối tượng bất biến hoặc dữ liệu tham gia equality không thể thay đổi.
- Không có mảng hoặc collection mutable bị lộ ra ngoài.
- Nếu dùng record, semantics của các component phù hợp với equality mong muốn.
- Nếu dùng BigDecimal, đã quyết định rõ scale có thuộc giá trị không.
- Nếu triển khai Comparable, đã xem xét quan hệ giữa compareTo() và equals().
- Có unit test cho equality, hashCode và hành vi trong collection.

## 12. Bài tập thực hành: Value Object cho khoảng thời gian giao hàng

Một hệ thống giao hàng có Value Object DeliveryWindow biểu diễn khoảng thời gian khách có thể nhận hàng, gồm:

- start: thời điểm bắt đầu.
- end: thời điểm kết thúc.
- timeZone: múi giờ áp dụng.

Chính sách giả định:

- start và end bắt buộc phải có.
- end phải sau start.
- timeZone là một phần của giá trị vì cùng thời điểm địa phương ở hai múi giờ có thể biểu diễn hai khoảng thời gian khác nhau.
- Hai DeliveryWindow bằng nhau nếu start, end và timeZone đều bằng nhau theo semantics đã chọn.
- Đối tượng không được thay đổi sau khi tạo.

Hãy thực hiện:

1. Xác định các thuộc tính tham gia equality.
2. Cài đặt DeliveryWindow bằng record hoặc final class.
3. Kiểm tra điều kiện end sau start trong constructor.
4. Cài đặt hoặc sử dụng equals/hashCode phù hợp.
5. Tạo hai instance có cùng giá trị và xác nhận chúng bằng nhau.
6. Thay đổi timeZone và xác nhận kết quả không bằng nhau theo chính sách giả định.
7. Dùng DeliveryWindow làm khóa HashMap và tra cứu bằng một instance tương đương.
8. Viết test cho các trường hợp null, khoảng thời gian không hợp lệ và equality.

### 12.1. Gợi ý triển khai bằng record

~~~java
public record DeliveryWindow(
    Instant start,
    Instant end,
    ZoneId timeZone
) {
    public DeliveryWindow {
        Objects.requireNonNull(start);
        Objects.requireNonNull(end);
        Objects.requireNonNull(timeZone);

        if (!end.isAfter(start)) {
            throw new IllegalArgumentException(
                "End must be after start"
            );
        }
    }
}
~~~

Record tự sinh equals() và hashCode() dựa trên ba component. Vì Instant và ZoneId là các kiểu giá trị bất biến, chúng phù hợp với ví dụ này.

Nếu nghiệp vụ muốn xem hai khoảng là bằng nhau khi chúng biểu diễn cùng một khoảng thời gian tuyệt đối bất kể múi giờ hiển thị, timeZone có thể không tham gia equality. Đó là một quyết định ngữ nghĩa khác và cần được xác nhận trước khi triển khai.

## Kết luận

Value Object được nhận diện bằng giá trị, vì vậy equals() và hashCode() phải phản ánh chính xác ý nghĩa nghiệp vụ của những thuộc tính cấu thành giá trị đó. equals() quyết định hai đối tượng có tương đương hay không; hashCode() giúp các cấu trúc dữ liệu dựa trên hash tìm và tổ chức những đối tượng đó một cách nhất quán.

Một Value Object tốt cần có semantics equality rõ ràng, bất biến và được kiểm thử. Hãy chú ý các kiểu dữ liệu có quy tắc so sánh đặc biệt như BigDecimal, các component mutable trong record và sự khác nhau giữa equals(), hashCode() và compareTo(). Khi những quy tắc này được định nghĩa đúng trong mô hình, Value Object có thể được so sánh, lưu trong collection và tái sử dụng một cách đáng tin cậy trong toàn bộ miền nghiệp vụ.


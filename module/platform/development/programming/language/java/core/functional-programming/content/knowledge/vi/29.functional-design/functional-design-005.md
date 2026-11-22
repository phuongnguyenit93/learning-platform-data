# Kết hợp quy tắc kiểm tra bằng `Predicate` có tên trong Java

## 1. Vì sao nên đặt tên cho quy tắc kiểm tra?

Trong ứng dụng Java, nhiều quyết định không dựa trên một điều kiện đơn lẻ. Ví dụ, một ứng viên đủ điều kiện đăng ký khi **đủ 18 tuổi, tài khoản hoạt động, đã xác minh và có email hợp lệ tối thiểu**.

Nếu đặt toàn bộ logic trong một lambda, mã có thể nhanh chóng trở nên khó đọc:

~~~java
List<Candidate> accepted = candidates.stream()
        .filter(c -> c != null
                && c.age() >= 18
                && c.active()
                && c.verified()
                && c.email() != null
                && !c.email().isBlank())
        .toList();
~~~

Ở ví dụ này, `Candidate` là một record do ứng dụng khai báo, được định nghĩa đầy đủ trong chương trình chạy độc lập ở phần sau.

Cách khác là **đặt tên cho các quy tắc nhỏ**, rồi kết hợp chúng:

~~~java
Predicate<Candidate> eligible = IS_NOT_NULL
        .and(IS_ADULT)
        .and(IS_ACTIVE)
        .and(IS_VERIFIED)
        .and(HAS_EMAIL);

List<Candidate> accepted = candidates.stream()
        .filter(eligible)
        .toList();
~~~

Khi đọc biểu thức, người học thấy rõ **điều kiện nghiệp vụ** thay vì phải giải mã một lambda dài. Từng Predicate cũng có thể được kiểm thử, tái sử dụng và ghép thành chính sách khác.

**Mục tiêu bài học:** hiểu `Predicate<T>`, cách khai báo quy tắc có tên bằng biến/hằng/method reference, phép ghép `and()`, `or()`, `negate()`, quy tắc short-circuit, cách đặt tên đúng ý nghĩa và xử lý `null`, kiểm thử quy tắc, tích hợp với `Stream.filter`, đồng thời tránh side effect và những lỗi logic dễ gặp.

## 2. `Predicate<T>` là gì?

`java.util.function.Predicate<T>` là functional interface biểu diễn một **điều kiện nhận giá trị kiểu `T` và trả `boolean`**. Phương thức trừu tượng duy nhất:

~~~java
boolean test(T value);
~~~

Ví dụ:

~~~java
Predicate<String> isLong = s -> s.length() >= 5;

System.out.println(isLong.test("Java"));   // false
System.out.println(isLong.test("Stream")); // true
~~~

Có thể viết bằng lambda hoặc method reference:

~~~java
Predicate<String> isBlank = String::isBlank;
Predicate<Integer> positive = n -> n > 0;
Predicate<String> nonNull = Objects::nonNull;
~~~

`Predicate` **không** trả thông báo lỗi hay thay đổi đầu vào. Nó chỉ báo một điều kiện là đúng hay sai. Nếu nghiệp vụ cần biết *tại sao* dữ liệu không hợp lệ, một kết quả validation có danh sách lỗi sẽ phù hợp hơn; xem phần 12.

Đặc tính quan trọng:

- Kiểu `T` là kiểu **đầu vào**, không phải kiểu đầu ra.
- `Predicate<String>` thường được truyền vào `Stream<String>.filter(...)`.
- Một Predicate có thể được gọi trực tiếp bằng `test(value)` hoặc truyền sang API nhận Predicate.
- Các phép ghép `and`, `or`, `negate` tạo **Predicate mới**, không sửa logic của Predicate gốc.
- Predicate có thể chứa lambda đóng trên biến bên ngoài (*captured variables*); để dễ suy luận và dùng song song, nên tránh phụ thuộc vào trạng thái mutable bị thay đổi trong lúc đánh giá.

## 3. Đặt tên quy tắc: từ lambda sang biểu thức nghiệp vụ

Giả sử record:

~~~java
record Candidate(
        String id,
        int age,
        boolean active,
        boolean verified,
        String email) {}
~~~

Khai báo các quy tắc có tên bằng hằng `static final`:

~~~java
static final Predicate<Candidate> IS_NOT_NULL =
        Objects::nonNull;

static final Predicate<Candidate> IS_ADULT =
        c -> c.age() >= 18;

static final Predicate<Candidate> IS_ACTIVE =
        Candidate::active;

static final Predicate<Candidate> IS_VERIFIED =
        Candidate::verified;

static final Predicate<Candidate> HAS_EMAIL =
        c -> c.email() != null && !c.email().isBlank();
~~~

Các tên này mô tả **điều gì được kiểm tra**, không mô tả cách thực thi:

- `IS_NOT_NULL`: đối tượng Candidate có tồn tại không?
- `IS_ADULT`: ứng viên đủ 18 tuổi không?
- `IS_ACTIVE`: tài khoản đang hoạt động không?
- `IS_VERIFIED`: trạng thái xác minh đã đạt chưa?
- `HAS_EMAIL`: email không null và không chỉ chứa khoảng trắng không?

`HAS_EMAIL` trong bài chỉ kiểm tra **không rỗng/không blank**, **không** kiểm chứng email đúng chuẩn địa chỉ email theo RFC hay tồn tại thực sự. Tên hàm nên phản ánh độ mạnh của kiểm tra; trong ứng dụng thực có thể đổi thành `HAS_NON_BLANK_EMAIL` để tránh kỳ vọng quá mức.

Các Predicate `IS_ADULT`, `IS_ACTIVE`, `IS_VERIFIED` và `HAS_EMAIL` trên đây giả định đầu vào **khác `null`**. Muốn kết hợp an toàn trước dữ liệu có thể null, đặt `IS_NOT_NULL` ở đầu chuỗi `and`, như phần tiếp theo.

### 3.1. Quy tắc có tham số: factory method

Không phải ngưỡng nào cũng nên hard-code thành hằng:

~~~java
static Predicate<Candidate> ageAtLeast(int minimumAge) {
    return c -> c != null && c.age() >= minimumAge;
}
~~~

Có thể tạo quy tắc theo ngữ cảnh:

~~~java
Predicate<Candidate> adult = ageAtLeast(18);
Predicate<Candidate> seniorProgram = ageAtLeast(21);
~~~

Ở đây tham số `minimumAge` được lambda capture; mỗi lời gọi method tạo/đại diện một chính sách riêng. Với tham số nguyên thủy không đổi, cách này dễ kiểm thử và an toàn hơn việc để predicate đọc một biến ngưỡng có thể bị nhiều thread cập nhật.

## 4. `and()`: tất cả các quy tắc phải đúng

Phương thức:

~~~java
default Predicate<T> and(Predicate<? super T> other);
~~~

Kết quả tương ứng với phép **AND logic**:

\[
(A \land B)(x)=A(x)\ \&\&\ B(x).
\]

Ví dụ:

~~~java
Predicate<Integer> positive = n -> n > 0;
Predicate<Integer> even = n -> n % 2 == 0;

Predicate<Integer> positiveEven = positive.and(even);

System.out.println(positiveEven.test(4));  // true
System.out.println(positiveEven.test(-2)); // false
System.out.println(positiveEven.test(3));  // false
~~~

`and()` dùng **short-circuit evaluation**: nếu Predicate bên trái trả `false`, Predicate bên phải **không được gọi**. Nhờ đó, kiểm tra null có thể bảo vệ các thao tác truy cập thuộc tính:

~~~java
Predicate<Candidate> safeAdult =
        IS_NOT_NULL.and(IS_ADULT);

System.out.println(safeAdult.test(null)); // false, không ném lỗi.
~~~

Khi truyền `null`:

1. `IS_NOT_NULL.test(null)` trả `false`.
2. Vì vế đầu của `and` sai, `IS_ADULT.test(null)` không được gọi.
3. Kết quả Predicate ghép là `false`.

**Thứ tự ghép có thể ảnh hưởng đến an toàn:**

~~~java
Predicate<Candidate> safe = IS_NOT_NULL.and(IS_ADULT);

// Không an toàn cho null:
// Predicate<Candidate> unsafe = IS_ADULT.and(IS_NOT_NULL);
~~~

Với `unsafe.test(null)`, quy tắc `IS_ADULT` phải truy cập `c.age()` trước nên sẽ ném `NullPointerException`. Hai quy tắc có thể tương đương logic trên miền dữ liệu non-null nhưng **không có cùng hành vi với null hay exception**.

Khi hàm đánh giá có chi phí khác nhau, thứ tự còn ảnh hưởng hiệu năng: đặt kiểm tra rẻ, có khả năng loại nhiều phần tử trước khi kiểm tra tốn kém có thể hữu ích, miễn không làm sai ngữ nghĩa và không phụ thuộc side effect.

## 5. `or()`: chỉ cần một quy tắc đúng

Phương thức:

~~~java
default Predicate<T> or(Predicate<? super T> other);
~~~

Tương ứng phép **OR logic**:

\[
(A \lor B)(x)=A(x)\ ||\ B(x).
\]

Ví dụ:

~~~java
Predicate<Integer> isZero = n -> n == 0;
Predicate<Integer> isNegative = n -> n < 0;

Predicate<Integer> nonPositive = isZero.or(isNegative);

System.out.println(nonPositive.test(0)); // true
System.out.println(nonPositive.test(-2)); // true
System.out.println(nonPositive.test(3)); // false
~~~

`or()` cũng short-circuit: nếu bên trái `true`, vế phải không cần chạy. Tuy nhiên, không dùng OR như một cách kiểm tra null tùy tiện:

~~~java
Predicate<Candidate> notNull = Objects::nonNull;
Predicate<Candidate> adult = c -> c.age() >= 18;

// Sai nếu kỳ vọng loại null an toàn:
// Predicate<Candidate> wrong = notNull.or(adult);
~~~

Với `null`, `notNull` trả false và OR buộc phải gọi `adult`; điều này có thể ném `NullPointerException`.

Nếu muốn “cho qua null hoặc là người trưởng thành”, hãy viết điều kiện tương ứng một cách rõ ràng:

~~~java
Predicate<Candidate> nullOrAdult =
        ((Predicate<Candidate>) Objects::isNull).or(IS_ADULT);
~~~

Trong code này, null cho kết quả true vì vế trái đã true; với non-null, vế phải đánh giá tuổi. Nhưng **cho phép null** là chính sách nghiệp vụ khác với **chỉ nhận Candidate hợp lệ**. Không sử dụng khi null phải được từ chối.

## 6. `negate()` và `Predicate.not()`

### 6.1. `negate()` đảo một quy tắc hiện có

~~~java
Predicate<Integer> isEven = n -> n % 2 == 0;
Predicate<Integer> isOdd = isEven.negate();

System.out.println(isOdd.test(3)); // true
System.out.println(isOdd.test(4)); // false
~~~

`negate()` tạo Predicate mà kết quả logic là phủ định của Predicate gốc. Nó **không sửa biến `isEven`**:

~~~java
System.out.println(isEven.test(4)); // true, vẫn vậy.
~~~

Với ứng viên:

~~~java
Predicate<Candidate> isNotActive = IS_ACTIVE.negate();
~~~

Lưu ý `isNotActive.test(null)` không an toàn, vì để phủ định kết quả, Predicate gốc vẫn phải chạy và truy cập `Candidate::active`. Thường nên ghép với kiểm tra non-null trước khi dùng:

~~~java
Predicate<Candidate> knownInactive =
        IS_NOT_NULL.and(IS_ACTIVE.negate());
~~~

Ở đây `knownInactive.test(null)` trả false. Điều đó cũng giúp phân biệt rõ giữa “không có Candidate” và “có Candidate nhưng không active”.

### 6.2. `Predicate.not()` thuận tiện với method reference

Từ Java 11 có phương thức tĩnh:

~~~java
static <T> Predicate<T> not(Predicate<? super T> target);
~~~

Dùng trực tiếp khi muốn phủ định method reference:

~~~java
List<String> names = List.of("Java", "", "Stream", "   ");

List<String> nonBlank = names.stream()
        .filter(Predicate.not(String::isBlank))
        .toList();

System.out.println(nonBlank); // [Java, Stream]
~~~

So sánh:

~~~java
Predicate<String> isBlank = String::isBlank;
List<String> nonBlank = names.stream()
        .filter(isBlank.negate())
        .toList();
~~~

Hai cách đều phù hợp. `Predicate.not(String::isBlank)` thường gọn khi biểu thức cần phủ định một method reference ngay tại chỗ; với quy tắc nghiệp vụ đã có tên, `IS_ACTIVE.negate()` có thể dễ đọc hơn.

**Cẩn thận:** `Predicate.not` không tự xử lý null hay exception của predicate bên trong. Nếu input là null, `String::isBlank` không nhận null an toàn; cần lọc `Objects::nonNull` trước.

### 6.3. Phủ định biểu thức ghép: luật De Morgan

Nếu `eligible = adult.and(active)`, thì:

~~~java
Predicate<Candidate> notEligible = eligible.negate();
~~~

về mặt logic có thể viết tương đương bằng De Morgan:

~~~java
Predicate<Candidate> notAdultOrInactive =
        IS_ADULT.negate().or(IS_ACTIVE.negate());
~~~

**Nhưng chỉ tương đương trên miền đầu vào mà các predicate đều được định nghĩa an toàn**, ví dụ Candidate khác null. Không suy rằng `IS_NOT_NULL.and(IS_ADULT).negate()` giống `IS_NOT_NULL.and(IS_ADULT.negate())` với null:

- `IS_NOT_NULL.and(IS_ADULT)` trả false với null.
- Phủ định toàn biểu thức sẽ trả **true** với null.
- `IS_NOT_NULL.and(IS_ADULT.negate())` trả **false** với null.

Đây là lỗi logic đáng chú ý khi tạo quy tắc “người bị từ chối”: bạn có thể muốn bỏ bản ghi null khỏi báo cáo hoặc coi null là một dạng bị từ chối. Hãy định nghĩa rõ mục tiêu trước khi phủ định toàn bộ biểu thức.

## 7. Kết hợp nhiều quy tắc có tên thành chính sách

Giả sử điều kiện đủ tư cách:

~~~java
static final Predicate<Candidate> ELIGIBLE =
        IS_NOT_NULL
                .and(IS_ADULT)
                .and(IS_ACTIVE)
                .and(IS_VERIFIED)
                .and(HAS_EMAIL);
~~~

Biểu thức này có nghĩa:

\[
\text{eligible}
= \text{notNull}
\land \text{adult}
\land \text{active}
\land \text{verified}
\land \text{hasEmail}.
\]

Đặt tên thành `ELIGIBLE` giúp các nơi sử dụng không cần lặp lại cấu trúc điều kiện:

~~~java
List<Candidate> accepted = candidates.stream()
        .filter(ELIGIBLE)
        .toList();

boolean canRegister = ELIGIBLE.test(candidate);

boolean hasAnyoneEligible = candidates.stream()
        .anyMatch(ELIGIBLE);
~~~

`Predicate` đóng vai trò **chính sách có thể truyền như dữ liệu**: một API khác có thể nhận tham số `Predicate<Candidate> policy` mà không cần biết chi tiết từng quy tắc.

### 7.1. Xây quy tắc “vi phạm trạng thái” bằng OR

~~~java
static final Predicate<Candidate> HAS_BAD_STATUS =
        IS_NOT_NULL.and(
                IS_ACTIVE.negate().or(IS_VERIFIED.negate()));
~~~

Ý nghĩa: Candidate tồn tại, và **không active hoặc chưa verified**. Do `IS_NOT_NULL` được kiểm tra trước, Predicate ghép từ chối null an toàn.

Nếu dùng `IS_ACTIVE.negate().or(IS_VERIFIED.negate())` trực tiếp với null, lỗi có thể phát sinh. Luôn xem toàn biểu thức, không chỉ từng thành phần.

### 7.2. Biểu diễn quy tắc bằng method có tên

Một số nhóm chọn tên phương thức thay cho hằng:

~~~java
static boolean isAdult(Candidate c) {
    return c != null && c.age() >= 18;
}

static boolean hasUsableEmail(Candidate c) {
    return c != null && c.email() != null && !c.email().isBlank();
}

Predicate<Candidate> rule =
        ((Predicate<Candidate>) Rules::isAdult)
                .and(Rules::hasUsableEmail);
~~~

Đoạn này giả định có lớp `Rules` sở hữu hai phương thức tĩnh; nó minh họa method reference, không phải tệp độc lập. Khi chỉ có một vài điều kiện, method có tên có thể dễ kiểm thử hơn; khi cần truyền hay ghép linh hoạt, giữ các `Predicate<T>` có tên đặc biệt tiện dụng.

## 8. Tích hợp với các thao tác Stream

### 8.1. `filter`: giữ những phần tử đạt quy tắc

~~~java
List<Candidate> accepted = candidates.stream()
        .filter(ELIGIBLE)
        .toList();
~~~

`filter` yêu cầu một `Predicate<? super T>` và giữ phần tử khi `test` trả true. Nó **không biến đổi** Candidate. Việc lọc không tự sửa danh sách nguồn.

### 8.2. `anyMatch`, `allMatch`, `noneMatch`

~~~java
boolean anyEligible = candidates.stream().anyMatch(ELIGIBLE);
boolean allEligible = candidates.stream().allMatch(ELIGIBLE);
boolean noneEligible = candidates.stream().noneMatch(ELIGIBLE);
~~~

- `anyMatch`: có ít nhất một phần tử đạt quy tắc.
- `allMatch`: mọi phần tử đều đạt quy tắc.
- `noneMatch`: không phần tử nào đạt quy tắc.

Ba terminal này có tính **short-circuit** và có thể dừng sớm; không giả định predicate được gọi trên toàn bộ nguồn. Trên Stream rỗng: `anyMatch` trả false, `allMatch` và `noneMatch` trả true theo quy tắc logic vacuous truth. Điều này quan trọng nếu nghiệp vụ muốn phân biệt dữ liệu rỗng với tập dữ liệu “tất cả hợp lệ”.

### 8.3. `dropWhile`, `takeWhile`, `removeIf`

`takeWhile` và `dropWhile` (Java 9+) cũng dùng Predicate, nhưng cách dùng **khác `filter`**:

~~~java
List<Integer> values = List.of(2, 4, 7, 8, 10);
Predicate<Integer> isEven = n -> n % 2 == 0;

System.out.println(values.stream()
        .takeWhile(isEven)
        .toList()); // [2, 4]

System.out.println(values.stream()
        .filter(isEven)
        .toList()); // [2, 4, 8, 10]
~~~

Với nguồn có thứ tự, `takeWhile` chỉ lấy **tiền tố liên tiếp** thỏa predicate, dừng tại 7; `filter` kiểm tra cả các phần tử sau đó khi cần kết quả đầy đủ.

`Collection.removeIf` cũng nhận Predicate, nhưng nó **sửa collection mutable gốc**, khác `Stream.filter` tạo luồng phần tử giữ lại:

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));
numbers.removeIf(n -> n % 2 == 0);
System.out.println(numbers); // [1, 3]
~~~

Không gọi `removeIf` trên cùng collection **từ bên trong callback đang duyệt Stream của collection đó**, vì vi phạm nguyên tắc non-interference.

## 9. Xử lý null có chủ ý

Null là một trong các lý do quan trọng cần thiết kế tên và thứ tự quy tắc tốt.

### 9.1. `Objects::nonNull` làm lớp bảo vệ

~~~java
Predicate<String> isNonBlank =
        ((Predicate<String>) Objects::nonNull)
                .and(s -> !s.isBlank());

System.out.println(isNonBlank.test(null));  // false
System.out.println(isNonBlank.test("   ")); // false
System.out.println(isNonBlank.test("Java")); // true
~~~

`Objects::nonNull` là method reference thuận tiện cho Predicate. Nó không phải toàn bộ policy: vế `and` thứ hai diễn đạt ràng buộc chuỗi không blank.

### 9.2. `Predicate.isEqual` xử lý so sánh bằng giá trị

`Predicate.isEqual(targetRef)` (Java 8+) tạo Predicate để so sánh theo `equals`, với cách xử lý null phù hợp:

~~~java
Predicate<String> isAdmin = Predicate.isEqual("admin");

System.out.println(isAdmin.test("admin")); // true
System.out.println(isAdmin.test("guest")); // false
System.out.println(isAdmin.test(null));    // false

Predicate<String> isNull = Predicate.isEqual(null);
System.out.println(isNull.test(null));     // true
~~~

`isEqual` không đồng nghĩa so sánh reference bằng `==`. Đối với target khác null, nó đánh giá equality theo quy tắc tương đương `target.equals(input)`; kết quả tùy implementation của `equals`. Với target null, Predicate kiểm tra đầu vào null.

### 9.3. “Không hợp lệ” có bao gồm null hay không?

Hai chính sách đều hợp lý trong hoàn cảnh khác nhau:

~~~java
Predicate<Candidate> rejectedIncludingNull =
        ELIGIBLE.negate();

Predicate<Candidate> rejectedNonNullOnly =
        IS_NOT_NULL.and(ELIGIBLE.negate());
~~~

- `rejectedIncludingNull.test(null) == true`: coi null là không đủ điều kiện.
- `rejectedNonNullOnly.test(null) == false`: chỉ quan tâm các Candidate có tồn tại nhưng không đủ điều kiện.

Đừng lẫn hai biểu thức. Khi dùng `Stream.filter` để tạo báo cáo, lựa chọn sẽ quyết định một phần tử null có được giữ trong kết quả “bị từ chối” hay không.

## 10. Khi nào nên sử dụng `Predicate` đặt tên?

Dùng Predicate có tên đặc biệt hữu ích khi:

1. **Một quy tắc lặp lại** tại nhiều điểm: service validation, bộ lọc danh sách, kiểm tra quyền hoặc báo cáo.
2. **Logic nghiệp vụ cần đọc được**: `ELIGIBLE`, `HAS_BAD_STATUS` có ý nghĩa hơn một chuỗi toán tử dài.
3. **Cần ghép linh hoạt** theo tình huống: áp dụng cả `HAS_EMAIL` và `IS_VERIFIED` ở màn hình A, nhưng chỉ `IS_ACTIVE` ở màn hình B.
4. **Cần kiểm thử độc lập** từng quy tắc, sau đó kiểm thử chính sách tổ hợp.
5. **Muốn thay implementation** của quy tắc mà giữ nguyên nơi gọi.
6. **Cần truyền policy như tham số** mà không tạo nhiều nhánh `if/else` trong API xử lý dữ liệu.

Tuy nhiên, không phải mọi điều kiện một dòng đều phải trở thành hằng static. Nếu chỉ dùng một lần và biểu thức hiển nhiên (`n -> n > 0`), giữ inline lambda có thể ngắn và rõ. Việc đặt tên có giá trị khi nó **giải thích mục đích** chứ không chỉ đặt tên `P1`, `CHECK1` hay `RULE_A`.

### 10.1. Chọn tên dương và nhất quán

Ưu tiên:

~~~java
IS_ACTIVE
IS_VERIFIED
HAS_NON_BLANK_EMAIL
IS_ADULT
ELIGIBLE
~~~

hơn các tên mơ hồ:

~~~java
VALID
CHECK
FLAG
PRED
TESTER
~~~

Nếu dùng tên `NOT_ACTIVE`, nên định nghĩa rõ nó là “Candidate tồn tại nhưng không hoạt động” hay “không có bằng chứng đang hoạt động, bao gồm cả null”. Cách đặt tên phải khớp policy trên toàn bộ miền dữ liệu hợp lệ.

### 10.2. Bất biến và tham số hóa

Nếu chính sách phụ thuộc ngưỡng do người dùng nhập, xây factory method với tham số immutable:

~~~java
static Predicate<Candidate> minAge(int threshold) {
    return c -> c != null && c.age() >= threshold;
}
~~~

Nếu policy phụ thuộc một tập các mã được phép:

~~~java
static Predicate<String> oneOf(Set<String> allowedCodes) {
    Set<String> snapshot = Set.copyOf(allowedCodes);
    return snapshot::contains;
}
~~~

`Set.copyOf` trả Set unmodifiable và từ chối null, giúp tránh việc tập `allowedCodes` bị sửa ngoài ý muốn sau khi tạo Predicate. Tuy nhiên, nó không sao chép sâu trạng thái của object phần tử nếu phần tử là kiểu mutable; với mã String bất biến, cách này phù hợp.

### 10.3. Sắp xếp kiểm tra theo tính phụ thuộc

Đặt điều kiện có thể bảo vệ vế sau trước:

~~~java
Predicate<Candidate> safe = IS_NOT_NULL
        .and(HAS_EMAIL)
        .and(IS_ACTIVE);
~~~

Bỏ thứ tự này có thể biến một chính sách trả false cho null thành một ngoại lệ. Với hai điều kiện vừa đắt vừa không có side effect, thứ tự có thể được cân nhắc theo chi phí và tỉ lệ loại bỏ thực tế.

## 11. Testability: kiểm thử đơn vị và bảng chân trị

Quy tắc có tên giúp mỗi điều kiện có thể được kiểm tra riêng bằng `test`:

~~~java
assert IS_ADULT.test(candidateAdult);
assert !IS_ADULT.test(candidateMinor);
assert ELIGIBLE.test(eligibleCandidate);
assert !ELIGIBLE.test(ineligibleCandidate);
~~~

Các dòng `assert` chỉ là minh họa; mặc định nhiều cấu hình Java không bật assertions nếu không dùng `-ea`. Trong dự án thật, ưu tiên framework unit test để thực hiện kiểm tra nhất quán khi chạy CI, chẳng hạn JUnit 5 (dependency ngoài JDK).

Một bảng kiểm thử chính sách `ELIGIBLE`:

| Candidate | Tuổi ≥18 | Active | Verified | Email non-blank | Kết quả |
| --- | --- | --- | --- | --- | --- |
| A | Đúng | Đúng | Đúng | Đúng | true |
| B | Sai | Đúng | Đúng | Đúng | false |
| C | Đúng | Sai | Đúng | Đúng | false |
| D | Đúng | Đúng | Sai | Đúng | false |
| E | Đúng | Đúng | Đúng | Sai | false |
| F | Đúng | Đúng | Đúng | Đúng | true |
| null | — | — | — | — | false nếu bắt đầu bằng `IS_NOT_NULL` |

Các thử nghiệm quan trọng nhất thường nằm ở **biên**: tuổi 17/18, email null/blank, trạng thái sai duy nhất, tất cả điều kiện đều đúng và đầu vào null.

### 11.1. Kiểm thử luật ghép một cách nhỏ gọn

Cho hai Predicate an toàn trên miền dữ liệu đang xét, có thể xác nhận:

- `A.and(B)` chỉ đúng khi cả A và B đúng.
- `A.or(B)` đúng khi ít nhất một vế đúng.
- `A.negate()` đảo kết quả A.
- `A.and(B)` giữ nguyên ý nghĩa của A nếu B luôn true.
- `A.or(B)` giữ nguyên ý nghĩa của A nếu B luôn false.

Những tính chất này dựa trên **hàm thuần, không ném lỗi và không có side effect**. Nếu Predicate ghi log, cập nhật bộ đếm, ném ngoại lệ hoặc đọc state mutable, thứ tự short-circuit có thể tạo hiệu ứng khác nhau mặc dù bảng chân trị logic trông tương đương.

## 12. Khi Predicate không đủ cho một hệ thống validation

`Predicate<T>` chỉ trả boolean; nó không mang lý do thất bại.

~~~java
boolean eligible = ELIGIBLE.test(candidate);
~~~

Nhưng form đăng ký có thể cần trả lời **những quy tắc nào không đạt**. Một cách tường minh là xây bộ kiểm tra trả kết quả có mã lỗi:

~~~java
record Violation(String code, String message) {}

static List<Violation> validateCandidate(Candidate c) {
    if (c == null) {
        return List.of(new Violation("MISSING", "Candidate is required"));
    }

    List<Violation> violations = new ArrayList<>();
    if (!IS_ADULT.test(c)) {
        violations.add(new Violation("AGE", "Age must be at least 18"));
    }
    if (!IS_ACTIVE.test(c)) {
        violations.add(new Violation("ACTIVE", "Account must be active"));
    }
    if (!IS_VERIFIED.test(c)) {
        violations.add(new Violation("VERIFIED", "Account must be verified"));
    }
    if (!HAS_EMAIL.test(c)) {
        violations.add(new Violation("EMAIL", "Email is required"));
    }
    return List.copyOf(violations);
}
~~~

Đây là ví dụ phương pháp, không phải class độc lập; cần khai báo `Candidate` và imports thích hợp. `List.copyOf` trả List unmodifiable theo hợp đồng và từ chối phần tử null.

Đừng dùng `and`/`or` kèm side effect chỉ để tích lũy mọi thông báo lỗi: **short-circuit** có nghĩa một số quy tắc không chạy, nên không thể kỳ vọng thu được đầy đủ lỗi. Hãy tách quyết định boolean nhanh bằng Predicate với quy trình thu thập lỗi riêng khi nghiệp vụ cần.

## 13. Chương trình Java 17+ hoàn chỉnh và stdout xác định

Tạo tệp **`NamedPredicateDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class NamedPredicateDemo {
    record Candidate(
            String id,
            int age,
            boolean active,
            boolean verified,
            String email) {}

    static final Predicate<Candidate> IS_NOT_NULL =
            Objects::nonNull;

    static final Predicate<Candidate> IS_ADULT =
            candidate -> candidate.age() >= 18;

    static final Predicate<Candidate> IS_ACTIVE =
            Candidate::active;

    static final Predicate<Candidate> IS_VERIFIED =
            Candidate::verified;

    static final Predicate<Candidate> HAS_EMAIL =
            candidate -> candidate.email() != null
                    && !candidate.email().isBlank();

    static final Predicate<Candidate> ELIGIBLE =
            IS_NOT_NULL
                    .and(IS_ADULT)
                    .and(IS_ACTIVE)
                    .and(IS_VERIFIED)
                    .and(HAS_EMAIL);

    static final Predicate<Candidate> BAD_STATUS =
            IS_NOT_NULL
                    .and(IS_ACTIVE.negate().or(IS_VERIFIED.negate()));

    static Predicate<Candidate> ageAtLeast(int age) {
        return candidate ->
                candidate != null && candidate.age() >= age;
    }

    public static void main(String[] args) {
        List<Candidate> candidates = Arrays.asList(
                new Candidate("A", 20, true, true, "a@example.test"),
                new Candidate("B", 17, true, true, "b@example.test"),
                new Candidate("C", 30, false, true, "c@example.test"),
                new Candidate("D", 21, true, false, "d@example.test"),
                new Candidate("E", 22, true, true, " "),
                new Candidate("F", 25, true, true, "f@example.test"),
                null);

        List<String> eligibleIds = candidates.stream()
                .filter(ELIGIBLE)
                .map(Candidate::id)
                .toList();

        List<String> rejectedIds = candidates.stream()
                .filter(IS_NOT_NULL.and(ELIGIBLE.negate()))
                .map(Candidate::id)
                .toList();

        List<String> badStatusIds = candidates.stream()
                .filter(BAD_STATUS)
                .map(Candidate::id)
                .toList();

        List<String> missingEmailIds = candidates.stream()
                .filter(IS_NOT_NULL.and(HAS_EMAIL.negate()))
                .map(Candidate::id)
                .toList();

        List<String> adultAt21 = candidates.stream()
                .filter(ageAtLeast(21))
                .map(Candidate::id)
                .toList();

        long adults = candidates.stream()
                .filter(IS_NOT_NULL.and(IS_ADULT))
                .count();

        List<String> nonBlank = List.of("Java", " ", "Stream", "")
                .stream()
                .filter(Predicate.not(String::isBlank))
                .toList();

        Predicate<String> isAdmin = Predicate.isEqual("admin");

        System.out.println("eligibleIds=" + eligibleIds);
        System.out.println("rejectedIds=" + rejectedIds);
        System.out.println("badStatusIds=" + badStatusIds);
        System.out.println("missingEmailIds=" + missingEmailIds);
        System.out.println("adultAt21=" + adultAt21);
        System.out.println("adultCount=" + adults);
        System.out.println("nullEligible=" + ELIGIBLE.test(null));
        System.out.println("adminMatch=" + isAdmin.test("admin"));
        System.out.println("otherMatch=" + isAdmin.test("guest"));
        System.out.println("nonBlank=" + nonBlank);
        System.out.println("anyEligible=" + candidates.stream()
                .anyMatch(ELIGIBLE));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac NamedPredicateDemo.java
java NamedPredicateDemo
~~~

**Kết quả stdout xác định:**

~~~text
eligibleIds=[A, F]
rejectedIds=[B, C, D, E]
badStatusIds=[C, D]
missingEmailIds=[E]
adultAt21=[C, D, E, F]
adultCount=5
nullEligible=false
adminMatch=true
otherMatch=false
nonBlank=[Java, Stream]
anyEligible=true
~~~

Giải thích:

1. `eligibleIds=[A, F]`: chỉ A và F đáp ứng đầy đủ tuổi, active, verified và email không blank.
2. `rejectedIds` loại null khỏi báo cáo rồi lấy phần tử không đạt `ELIGIBLE`; vì vậy là B, C, D, E.
3. `badStatusIds=[C, D]`: C không active, D chưa verified. Candidate null bị loại nhờ `IS_NOT_NULL`.
4. `missingEmailIds=[E]`: E có email chỉ gồm khoảng trắng, không phải email non-blank.
5. `adultAt21=[C, D, E, F]`: factory method tạo predicate ngưỡng 21, và tự bảo vệ null.
6. `adultCount=5`: chỉ B chưa đủ 18 tuổi; null bị loại.
7. `nullEligible=false` chứng minh `IS_NOT_NULL` ở đầu chuỗi AND giúp đánh giá null an toàn.
8. `Predicate.isEqual("admin")` trả true cho `"admin"` và false cho `"guest"`.
9. `Predicate.not(String::isBlank)` loại chuỗi rỗng hoặc chỉ chứa khoảng trắng.
10. `anyEligible=true` vì ít nhất A hoặc F đáp ứng policy; `anyMatch` có thể dừng sớm.

Chương trình sử dụng `Arrays.asList` để biểu diễn danh sách có một phần tử null; khác với `List.of`, vốn không chấp nhận phần tử null. Tất cả các pipeline tạo kết quả đều duyệt nguồn List tuần tự, nên thứ tự các ID được in là ổn định.

## 14. Những lỗi phổ biến

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Đặt toàn bộ logic nghiệp vụ trong một lambda quá dài | Khó kiểm thử và tái sử dụng | Tách điều kiện thành Predicate có tên |
| Cho rằng `and` và `or` luôn gọi cả hai vế | Chúng short-circuit | Không đặt side effect bắt buộc ở vế có thể bị bỏ qua |
| Viết `IS_ADULT.and(IS_NOT_NULL)` rồi truyền null | `IS_ADULT` sẽ gọi trước và có thể ném NPE | Dùng `IS_NOT_NULL.and(IS_ADULT)` |
| Viết `IS_NOT_NULL.or(IS_ADULT)` để bảo vệ null | Khi null, OR gọi vế phải nên vẫn lỗi | Dùng AND hoặc định nghĩa chính sách “cho phép null” rõ ràng |
| Gọi `IS_ACTIVE.negate().test(null)` | Negate không thêm null guard | Dùng `IS_NOT_NULL.and(IS_ACTIVE.negate())` |
| Phủ định toàn `ELIGIBLE` và ngỡ null bị loại | `!false = true` nên null có thể được giữ | Ghép `IS_NOT_NULL.and(ELIGIBLE.negate())` nếu chỉ chọn bản ghi tồn tại |
| Nhầm `Predicate.not` có trong Java 8 | Static method này có từ Java 11 | Dùng Java 11+ hoặc predicate có tên với `negate` |
| Nhầm `Predicate.isEqual` dùng so sánh reference | `isEqual` kiểm tra equality theo `equals` | Hiểu ngữ nghĩa equals/null |
| Đặt tên `HAS_EMAIL` nhưng kỳ vọng validate chuẩn email | Chỉ kiểm tra có nội dung | Đặt tên phản ánh độ mạnh của quy tắc |
| Dùng `Predicate` để thu thập mọi lỗi validation | Boolean không có lý do; short-circuit bỏ bớt phép kiểm tra | Dùng kết quả validation có danh sách lỗi |
| Capture một `List` mutable rồi dùng Predicate song song | State có thể thay đổi giữa các lượt, tạo race | Snapshot/immutable value hoặc đồng bộ phù hợp |
| Dùng `removeIf` bên trong `stream().filter` trên cùng nguồn | Can thiệp collection đang được duyệt | Tách pha mutation khỏi Stream |
| Tái sử dụng một Stream đã chạy terminal | Stream chỉ tiêu thụ một lần | Tạo pipeline mới từ nguồn |
| Dùng Predicate tham chiếu đối tượng mutable rồi coi kết quả luôn cố định | Điều kiện có thể đổi khi trạng thái đối tượng đổi | Định nghĩa ownership, immutability và ngữ cảnh đánh giá |

## 15. Câu hỏi tự kiểm tra và lời giải

**Câu 1.** Với `Predicate<Integer> positive = n -> n > 0` và `even = n -> n % 2 == 0`, giá trị `positive.and(even).test(-2)` là gì?

**Lời giải:** `false`. Positive kiểm tra trước và trả false, nên even không cần chạy.

**Câu 2.** `positive.or(even).test(-2)` có trả true không?

**Lời giải:** Có. `positive(-2) == false`, nhưng `even(-2) == true`.

**Câu 3.** Vì sao `Objects::nonNull` thường đặt ở đầu `and` khi các quy tắc còn lại truy cập thuộc tính?

**Lời giải:** AND short-circuit. Nếu đối tượng null, điều kiện đầu false, các quy tắc có thể dereference object không chạy, tránh `NullPointerException`.

**Câu 4.** `ELIGIBLE.negate()` và `IS_NOT_NULL.and(ELIGIBLE.negate())` khác nhau thế nào với null?

**Lời giải:** `ELIGIBLE.test(null)` là false, nên phủ định toàn biểu thức trả true. Biểu thức thứ hai trả false vì kiểm tra non-null ở đầu.

**Câu 5.** Để lọc chuỗi không blank bằng method reference, cách nào đúng trên Java 17?

**Lời giải:** `stream.filter(Predicate.not(String::isBlank))`, nếu đầu vào không null. Nếu có null, lọc `Objects::nonNull` trước.

**Câu 6.** Khi policy cần ngưỡng tuổi tùy từng chiến dịch, nên khai báo hằng `IS_ADULT` hay tạo `ageAtLeast(minimumAge)`?

**Lời giải:** Factory method `ageAtLeast(minimumAge)` giúp cấu hình ngưỡng khác nhau theo lần sử dụng; hằng chỉ phù hợp với quy tắc cố định.

**Câu 7.** Nếu chỉ có `Predicate<Candidate>`, có thể tự biết ứng viên thất bại vì tuổi hay email không?

**Lời giải:** Không. Predicate chỉ trả boolean; muốn ghi từng lý do phải đánh giá quy tắc và tạo kết quả validation chứa mã lỗi/thông báo.

**Câu 8.** `allMatch(policy)` với Stream rỗng trả gì? Có đủ để kết luận “mọi ứng viên đã đăng ký đều hợp lệ” không?

**Lời giải:** Nó trả true theo logic vacuous truth. Nếu nghiệp vụ đòi ít nhất một ứng viên, phải kiểm tra thêm điều kiện không rỗng.

**Câu 9.** `Predicate<String> isAdmin = Predicate.isEqual("admin")`; `isAdmin.test(null)` có ném `NullPointerException` không?

**Lời giải:** Không. Nó trả false; `Predicate.isEqual` xử lý null theo hợp đồng của API.

## 16. Ghi nhớ

`Predicate<T>` đại diện một phép kiểm tra kiểu `T -> boolean`. Đặt tên cho các Predicate giúp **quy tắc nghiệp vụ rõ ràng, dễ thử nghiệm và tái sử dụng**.

- Dùng `and` khi **tất cả** điều kiện phải đúng, `or` khi cần **ít nhất một** điều kiện, `negate` hoặc `Predicate.not` khi cần phủ định.
- `and`/`or` **short-circuit**; thứ tự ghép ảnh hưởng đến null safety, exception và side effect.
- Đặt `Objects::nonNull` phía trước các predicate dereference trong chuỗi AND nếu đầu vào có thể null.
- Cân nhắc kỹ ý nghĩa phủ định: “không hợp lệ” có thể bao gồm null, còn “đối tượng tồn tại nhưng không hợp lệ” thì không.
- Dùng named predicates làm tham số cho `filter`, `anyMatch`, `allMatch`, `noneMatch` và những API khác nhận Predicate.
- Dùng **factory method** để tạo quy tắc có tham số, tránh state mutable chia sẻ nếu muốn chạy song song.
- `Predicate` trả boolean, không thay thế mô hình validation nhiều thông báo lỗi; tách việc thu thập lỗi ra một cơ chế rõ ràng.
- Luôn kiểm thử các trường hợp biên, null, quy tắc đơn lẻ và tổ hợp.

Khi chính sách có nhiều điều kiện, một biểu thức như `IS_NOT_NULL.and(IS_ADULT).and(IS_ACTIVE).and(IS_VERIFIED).and(HAS_EMAIL)` thường là cách trình bày dễ bảo trì hơn một lambda dài, miễn từng quy tắc có tên chính xác và cùng tuân thủ hợp đồng dữ liệu.

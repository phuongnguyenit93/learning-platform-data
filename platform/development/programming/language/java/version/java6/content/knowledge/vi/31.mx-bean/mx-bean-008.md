# Wildcard trong giá trị khóa ObjectName khi làm việc với MXBean

**`javax.management.ObjectName`** là định danh của một MBean hoặc MXBean trong Java Management Extensions (JMX). Ngoài việc biểu diễn **một tên cụ thể**, `ObjectName` còn có thể biểu diễn **mẫu truy vấn** để tìm nhiều MBeans theo domain, danh sách khóa và **giá trị khóa**. Điểm trọng tâm của bài này là hai ký tự wildcard **`*`** và **`?`** khi nằm trong **giá trị** như `name=worker*` hay `region=e?`.

Một sự khác biệt nhỏ có thể gây lỗi lớn: nếu bạn muốn đăng ký MXBean có tên thật là `alpha*literal`, viết `name=alpha*literal` sẽ tạo **pattern**, không phải tên literal. **Đưa giá trị vào dấu nháy kép cũng chưa đủ**: `name="alpha*"` vẫn là một **property-value pattern**. Khi cần một giá trị literal có `*`, `?`, dấu phẩy, dấu bằng, dấu nháy hoặc ký tự đặc biệt, hãy dùng **`ObjectName.quote(rawValue)`** để mã hóa/escape chính xác.

Bài thuộc nhóm **MXBean** và sử dụng các API còn áp dụng trong **Java 17+ / Java SE 26**. Một chương trình Java độc lập đăng ký **chín MXBeans trong một MBeanServer cục bộ**, minh họa truy vấn wildcard và các lỗi thường gặp. Code đã biên dịch với `javac --release 17` và chạy thành công trên JDK trong môi trường làm việc, **28/28 kiểm tra PASS**; không khởi động JMX remote connector hoặc mở cổng mạng.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Phân biệt `ObjectName` định danh chính xác và `ObjectName` dạng pattern dùng cho truy vấn.
2. Viết cú pháp `domain:key=value,key2=value2` và nêu giới hạn của tên domain, tên khóa, giá trị khóa.
3. Hiểu `*` khớp **0 hoặc nhiều ký tự**, `?` khớp **đúng 1 ký tự** khi dùng trong property value pattern.
4. Giải thích vì sao wildcard **trong dấu nháy kép** vẫn có thể có ý nghĩa pattern.
5. Dùng `ObjectName.quote` và `ObjectName.unquote` để tạo/đọc giá trị literal chứa `*`, `?`, `,`, `=`, dấu nháy và backslash.
6. Phân biệt **property-value pattern**, **property-list pattern** và **domain pattern**.
7. Dùng `isPattern()`, `isPropertyValuePattern()`, `isPropertyValuePattern("name")`, `isPropertyListPattern()` và `isDomainPattern()`.
8. Hiểu rằng pattern `name=alpha*` **không mặc định cho phép các khóa bổ sung**: cần `,*` khi cần khớp thêm properties.
9. Phân biệt pattern `name=alpha*,*` với `name="alpha*",*` nếu registry chứa cả giá trị quoted và unquoted.
10. Đăng ký MXBean bằng **non-pattern ObjectName**, truy vấn bằng `MBeanServer.queryNames(pattern, null)`.
11. Dùng `StandardMBean(implementation, interface, true)` và `JMX.newMXBeanProxy` với typed MXBean.
12. Biết key-property order không làm tên khác nhau, `getCanonicalName()` giúp biểu diễn ổn định.
13. Ngăn việc ghép giá trị đầu vào thành tên JMX làm thay đổi số lượng properties hoặc mở rộng wildcard ngoài ý muốn.
14. Không dùng wildcard query như cơ chế authentication/authorization; bảo vệ JMX management interface.

## 2. ObjectName là gì?

Cú pháp tổng quát:

```text
domain:key1=value1,key2=value2
```

Ví dụ một MXBean giám sát cache:

```text
com.example.jmx:type=Cache,name=alpha1,region=eu
```

- **Domain**: `com.example.jmx`, dùng để phân nhóm MBeans. Kiểu reverse-DNS giúp giảm va chạm tên giữa thư viện và ứng dụng.
- **Key property** `type=Cache`: một thuộc tính của tên. `type` là **khóa**, `Cache` là **giá trị**.
- **Key property** `name=alpha1`: định danh cache trong nhóm.
- **Key property** `region=eu`: chỉ khu vực, được chọn làm một phần danh tính của MXBean ở ví dụ.
- **Thứ tự properties không quan trọng với equality**. `type=Cache,name=alpha1,region=eu` và `region=eu,name=alpha1,type=Cache` là cùng một `ObjectName`.

`ObjectName` là immutable. Nó **không phải** MXBean implementation, không chứa metrics, không thực hiện network I/O và không cấp quyền truy cập. JMX server sử dụng tên đó để đăng ký và truy vấn các MBeans.

### 2.1. Phân biệt MXBean và ObjectName

Một **MXBean** mô tả management interface, thường gồm getters/setters/operations có kiểu dữ liệu thích hợp với JMX Open Types. `ObjectName` đơn giản là **tên đăng ký** của instance.

Ví dụ interface:

```java
public interface CacheStatsMXBean {
    long getHitCount();
    String getState();
}
```

Đây là **đoạn interface minh họa**. Chương trình hoàn chỉnh mục 9 định nghĩa class, tạo `StandardMBean(..., true)`, đăng ký với `MBeanServer` và gọi `JMX.newMXBeanProxy`.

Các quy tắc wildcard của `ObjectName` áp dụng cho **MBean lẫn MXBean**. Không có cú pháp wildcard riêng biệt chỉ vì interface tên kết thúc bằng `MXBean`.

### 2.2. Giới hạn ký tự trong domain, key và value

| Phần | Ví dụ | Quy tắc quan trọng |
| --- | --- | --- |
| Domain | `com.example.jmx` | Không chứa `:`. Chứa `*` hay `?` thì là domain pattern. |
| Key name | `type`, `name`, `region` | Phải không rỗng; không chứa `,`, `=`, `:`, `*` hoặc `?`. Không có duplicate keys. |
| Unquoted value | `alpha1`, `alpha*`, `e?` | Không chứa `,`, `=`, `:` hay dấu nháy; `*`/`?` là wildcard. |
| Quoted value | `"alpha zone"`, `"alpha\*literal"` | Quotes và backslash escaping có ý nghĩa; wildcard **không escape** vẫn là pattern. |
| Key-property list | `type=Cache,name=alpha1` | Các cặp khóa–giá trị cách nhau bằng dấu phẩy. |
| Wildcard list | `type=Cache,*` | Dấu `*` là phần tử **riêng** trong property list, cho phép thêm các properties khác. |

**Khoảng trắng có ý nghĩa** trong tên. `name=alpha1` khác `name= alpha1`; các khoảng trắng quanh dấu phẩy có thể vô tình trở thành phần của tên khóa. Không tự động `trim()` cấu trúc tên mà không có quy tắc rõ ràng.

### 2.3. Tên chính xác và tên mẫu

```text
Tên chính xác:
  com.example.jmx:type=Cache,name=alpha1,region=eu

Mẫu giá trị:
  com.example.jmx:type=Cache,name=alpha*,region=eu

Mẫu cho phép thêm properties:
  com.example.jmx:type=Cache,name=alpha*,*

Mẫu domain và property-list:
  com.example.*:type=Cache,*
```

Một `ObjectName` có pattern được dùng để chọn **nhiều** MBeans, không phải định danh một instance đăng ký. Với code dynamic, nên kiểm tra `name.isPattern() == false` trước `registerMBean`.

## 3. Hai wildcard của giá trị khóa: * và ?

Với **property-value pattern**:

- **`*`** khớp một chuỗi **0 hoặc nhiều** ký tự.
- **`?`** khớp **chính xác một** ký tự.
- Nhiều ký tự có thể kết hợp: `name=api-*-?`.
- Đây là matching trong **giá trị của cùng khóa**, không phải cú pháp chọn nhiều key names.
- Việc khớp **phân biệt chữ hoa/thường**; `ALPHA*` khác `alpha*`.

Ví dụ ý nghĩa khi giá trị **không quote**:

| Pattern | Giá trị khớp | Giá trị không khớp |
| --- | --- | --- |
| `name=alpha*` | `alpha`, `alpha1`, `alpha-prod` | `beta` |
| `name=alpha?` | `alpha1`, `alphaX` | `alpha`, `alpha123` |
| `name=*prod` | `prod`, `west-prod` | `product-us` |
| `region=e?` | `eu`, `en` | `e`, `europe` |
| `type=Cache` | `Cache` | `cache` |
| `name=*` | Mọi giá trị hợp lệ của key `name` theo pattern. | Không tự cho phép thiếu key `name`. |

**Lưu ý thứ hai của bảng:** một match property value chỉ xét giá trị của **khóa được nêu**. Nếu pattern không có `name`, nó không đặt điều kiện lên giá trị của `name`; nếu pattern có `name=*`, nó yêu cầu có key `name` trong tên cụ thể.

### 3.1. Vì sao tên có dấu * lại thành pattern?

```java
ObjectName valuePattern = new ObjectName(
        "com.example.jmx:type=Cache,name=alpha*,region=eu");

System.out.println(valuePattern.isPattern());              // true
System.out.println(valuePattern.isPropertyValuePattern()); // true
System.out.println(valuePattern.isPropertyValuePattern("name")); // true
```

Đây là **mảnh code**; cần `import javax.management.ObjectName` và method xử lý checked exception. Ký tự `*` đang dùng để tìm tên bắt đầu `alpha`, chứ không miêu tả một cache có tên literal `alpha*`.

### 3.2. Quoted value vẫn có thể là wildcard

Một nhầm lẫn thường thấy:

```text
name="alpha*"
```

Đây **vẫn là pattern** nếu `*` không được escape bên trong quoted value. Javadoc `ObjectName` nêu rõ dấu `*`/`?` bên trong cặp quotes được coi là wildcard trừ khi đứng sau backslash hợp lệ. Trong Java:

```java
ObjectName quotedPattern = new ObjectName(
        "com.example.jmx:type=Cache,name=\"alpha*\",region=eu");
System.out.println(quotedPattern.isPropertyValuePattern("name")); // true
```

Đây là mảnh code. **Quotes không tự tắt wildcard**, đặc biệt nguy hiểm nếu code chỉ bọc `"` quanh giá trị của user rồi tin là đã escape an toàn.

## 4. Dùng ObjectName.quote để giữ * và ? dưới dạng literal

Khi dữ liệu là **tên thực của một instance**, luôn xem nó là **literal value**, không phải pattern. Dùng:

```java
String rawName = "alpha*literal";
String encodedValue = ObjectName.quote(rawName);

ObjectName exact = new ObjectName(
        "com.example.jmx:type=Cache,name="
                + encodedValue + ",region=eu");

System.out.println(exact.isPattern()); // false
```

`ObjectName.quote("alpha*literal")` trả chuỗi tên có dấu quotes và wildcard được escape, tương đương cách viết trong văn bản JMX:

```text
name="alpha\*literal"
```

Cũng tương tự, `ObjectName.quote("alpha?literal")` tạo:

```text
name="alpha\?literal"
```

Ký tự backslash `\` trong **quoted value** là escape cho `*` hoặc `?`. Trong **Java String literal** khi tự viết escape bằng tay, dấu backslash thường phải được viết thành `\\`. Chính vì thế `ObjectName.quote(raw)` an toàn, dễ đọc hơn xây escapes thủ công.

### 4.1. quote còn bảo vệ dấu phẩy và dấu bằng

Giả sử tên instance do người dùng nhập là:

```text
sales,west=1
```

Sai:

```java
String unsafe = "com.example.jmx:type=Cache,name="
        + userInput + ",region=ap";
ObjectName parsed = new ObjectName(unsafe);
```

Nếu `userInput == "sales,west=1"`, tên trên bị hiểu thành **4 key properties**: `type=Cache`, `name=sales`, `west=1`, `region=ap`. Đoạn này có thể **không ném exception** mà vẫn mang sai cấu trúc tên.

Đúng:

```java
ObjectName safe = new ObjectName(
        "com.example.jmx:type=Cache,name="
        + ObjectName.quote(userInput)
        + ",region=ap");
```

Khi quote đúng, `getKeyPropertyList().size() == 3`, còn `ObjectName.unquote(safe.getKeyProperty("name"))` cho lại `sales,west=1`.

**Quy tắc bảo vệ:** đừng nối trực tiếp raw user input vào `ObjectName`. Coi việc quote là biện pháp giữ **cấu trúc tên đúng và không tạo pattern ngoài ý muốn**. Nó không thay thế authentication, authorization hoặc tenant isolation của JMX management operations.

### 4.2. Những ký tự ObjectName.quote xử lý

Theo Javadoc Java SE 26, `ObjectName.quote(String)` xử lý:

- Dấu nháy kép `"` bằng escape.
- `*` bằng `\*`.
- `?` bằng `\?`.
- Backslash bằng hai dấu backslash.
- Newline bằng chuỗi escape `\n` trong quoted value.

Trên `ObjectName`, **raw newline không hợp lệ**, nhưng quoted escaped newline có thể biểu diễn nội dung newline. Chương trình mục 9 kiểm tra `quoteProtectsSpecialCharacters=PASS` bằng dữ liệu thử có dấu phẩy, bằng, dấu hai chấm, backslash, quotes, wildcard và newline.

### 4.3. ObjectName.unquote chỉ dùng với quoted value

`ObjectName.getKeyProperty("name")` trả **representation** của giá trị khóa. Nếu lúc đăng ký bạn dùng `ObjectName.quote(...)`, giá trị trả về vẫn chứa quotes/escapes. Để lấy lại string nguyên bản:

```java
String original = ObjectName.unquote(
        registeredName.getKeyProperty("name"));
```

Đây là mảnh code khi `registeredName` đã được tạo từ **quoted name**. `unquote` yêu cầu dữ liệu ở dạng quoted hợp lệ, không nên gọi bừa trên mọi unquoted property value. Nếu hệ thống có cả quoted và unquoted values, hãy xác định quy ước serialization trước khi decode.

### 4.4. Không dùng escape kiểu shell/SQL để thay quote

Các đoạn như `name=alpha\*literal` **không phải cách an toàn thay thế** `ObjectName.quote` trong một unquoted value. Với `ObjectName`, quy tắc escape backslash cho wildcard áp dụng trong **quoted value**. Trên JDK đã kiểm thử, `name=alpha\*literal` không quote vẫn là property-value pattern, không phải tên literal. Dùng `ObjectName.quote` để loại bỏ mơ hồ.

## 5. Ba cấp độ pattern khác nhau

`ObjectName` có ba chiều pattern:

| Loại | Ví dụ | Vai trò | API kiểm tra |
| --- | --- | --- | --- |
| **Domain pattern** | `com.example.*:type=Cache,region=eu` | Domain có `*` hoặc `?`. | `isDomainPattern()` |
| **Property-value pattern** | `name=alpha*`, `region=e?` | Wildcard bên trong **giá trị khóa**. | `isPropertyValuePattern()`, `isPropertyValuePattern(key)` |
| **Property-list pattern** | `type=Cache,*` | Cho phép **thêm các key properties** ngoài ones đã nêu. | `isPropertyListPattern()` |

`isPropertyPattern()` là true nếu có **value pattern hoặc list pattern hoặc cả hai**. `isPattern()` là true nếu có **domain pattern hoặc property pattern**.

### 5.1. Property-value pattern không giống property-list pattern

Xét ba MXBeans:

```text
com.example.jmx:type=Cache,name=alpha,region=eu
com.example.jmx:type=Cache,name=alpha1,region=eu
com.example.jmx:type=Cache,name=alpha2,region=us
```

Hai pattern:

```text
com.example.jmx:type=Cache,name=alpha*
com.example.jmx:type=Cache,name=alpha*,*
```

Mẫu thứ nhất **không khớp** ba tên trên bởi pattern chỉ liệt kê các keys `type` và `name`, còn tên đăng ký có thêm `region`. Mẫu thứ hai với **`,*`** cho phép key `region` bổ sung, nên tìm đủ ba tên.

**Đây là lỗi phổ biến nhất khi queryNames trả tập rỗng dù nhìn thấy prefix đúng.**

### 5.2. Dấu * ngoài property value có nghĩa riêng

Trong:

```text
domain:type=Cache,*
```

`*` là một **phần tử riêng trong danh sách thuộc tính**, có nghĩa cho phép bất kỳ số lượng key properties còn lại, không phải đang so giá trị khóa nào.

Trong:

```text
domain:type=Cache,name=*
```

`*` nằm **sau dấu `=`**, nghĩa nó là **wildcard của giá trị name**; không có quyền thêm key ngoài hai keys đã liệt kê.

Trong:

```text
domain:type=Cache,name=*,*
```

có **cả hai loại wildcard**: mọi giá trị name và cho phép properties bổ sung.

### 5.3. Không có wildcard cho phần tên key

Một property key phải là tên cụ thể hợp lệ. Ví dụ `nam*=alpha` không phải cách chọn các keys bắt đầu bằng `nam`. Đặt wildcard ở vị trí key vi phạm syntax. Muốn biết instance có key `name` hay `service`, truy vấn rộng có giới hạn sau đó phân loại keys, hoặc áp một naming convention thống nhất.

## 6. Quoted wildcard và unquoted wildcard có thể cho kết quả khác nhau

Điều này đặc biệt dễ bị bỏ sót nếu ứng dụng đôi lúc dùng `ObjectName.quote`, đôi lúc ghép unquoted names.

Giả sử registry có:

```text
Unquoted:
  name=alpha
  name=alpha1
  name=alpha2

Quoted:
  name="alpha zone"
  name="alpha\*literal"
  name="alpha\?literal"
  name="alphaX"
```

Mọi tên trên còn có `type=Cache` và `region=...`. Trên JDK được kiểm thử:

| Truy vấn có thêm `,*` | Kết quả | Vì sao |
| --- | --- | --- |
| `name=alpha*,*` | Ba **unquoted** names. | Prefix match trên representation không có quotes. |
| `name=alpha?,*` | Hai unquoted `alpha1` và `alpha2`. | `?` khớp đúng một ký tự. |
| `name="alpha*",*` | Bốn **quoted** names. | Quotes là một phần representation, wildcard vẫn có ý nghĩa. |
| `name="alpha?",*` | Một quoted `"alphaX"`. | `?` khớp đúng một ký tự trước quote đóng. |
| `name="alpha\*literal",region=eu` | Đúng tên quoted có literal `*`. | Dấu `\*` là escaped literal trong quoted value. |

**Vì sao dấu quotes quan trọng?** Javadoc quy định quotes và backslashes của quoted values được xem là một phần giá trị `ObjectName`. Vì vậy pattern trên representation không quote và pattern trên representation có quote không nhất thiết tương đương.

Hệ quả:

- Nếu **luôn quote string values lúc đăng ký**, khi xây pattern tìm theo tên bạn cần nhất quán với **quoted representation**.
- Nếu registry có cả quoted/unquoted names, một wildcard pattern duy nhất có thể không bao phủ hết như bạn nghĩ.
- Đừng tự suy diễn rằng `ObjectName.quote(prefix + "*")` là cách tạo prefix pattern: hàm `quote` sẽ **escape dấu `*` thành literal**, vì nó được thiết kế cho **giá trị thật**, không phải wildcard query.
- Nếu cần pattern động, xây theo **một naming convention cố định**, escape mọi phần user-controlled, sau đó thêm wildcard do code tin cậy quyết định; viết tests cả quoted/unquoted cases.
- Với phần lớn ứng dụng, chọn một convention đơn giản **quote mọi string dynamic values khi đăng ký** và thiết kế các query patterns tương thích ngay từ đầu.

## 7. API kiểm tra pattern và truy vấn MBeanServer

Một vài methods hữu ích:

```java
ObjectName pattern = new ObjectName(
        "com.example.jmx:type=Cache,name=alpha*,*");

boolean anyPattern = pattern.isPattern();
boolean domainPattern = pattern.isDomainPattern();
boolean valuePattern = pattern.isPropertyValuePattern();
boolean namePattern = pattern.isPropertyValuePattern("name");
boolean listPattern = pattern.isPropertyListPattern();
boolean propertyPattern = pattern.isPropertyPattern();
```

Đây là mảnh code; `isPropertyValuePattern("name")` có thể ném `IllegalArgumentException` nếu key được yêu cầu không tồn tại, và `NullPointerException` nếu key là null.

### 7.1. queryNames và tập kết quả

```java
Set<ObjectName> matchedNames = server.queryNames(pattern, null);
```

`server` là một `MBeanServer` đã được tạo. Tham số `null` nghĩa không áp thêm `QueryExp` filter. Kết quả là một `Set<ObjectName>`, **không bảo đảm thứ tự lặp**. Nếu cần output có thứ tự ổn định:

```java
List<String> ordered = matchedNames.stream()
        .map(ObjectName::getCanonicalName)
        .sorted()
        .toList();
```

Hai mảnh code này yêu cầu imports tương ứng. Khi các MBeans đăng ký/hủy động, tập kết quả có thể thay đổi giữa những lần gọi `queryNames`; đừng coi query là ảnh chụp bất biến của toàn hệ thống khi có concurrency.

### 7.2. apply(ObjectName) để đối chiếu một tên

`ObjectName.apply(otherName)` trả true nếu pattern khớp một **non-pattern ObjectName**, hoặc hai non-pattern names bằng nhau. Theo Javadoc, nếu `otherName` **bản thân là pattern**, `apply` trả false.

```java
ObjectName prefix = new ObjectName(
        "com.example.jmx:type=Cache,name=alpha*,*");
ObjectName exact = new ObjectName(
        "com.example.jmx:type=Cache,name=alpha1,region=eu");

System.out.println(prefix.apply(exact)); // true
System.out.println(prefix.apply(prefix)); // false
```

Đây là mảnh code. `apply` không có nghĩa gọi qua JMX server hoặc kiểm tra authorization; nó so hai `ObjectName` theo matching semantics của JMX.

### 7.3. isRegistered và registerMBean không phải wildcard query

`MBeanServer.registerMBean(mbean, name)` cần định danh **một MBean cụ thể**; pattern không thích hợp và runtime có thể ném `RuntimeOperationsException`. Trên JDK thử nghiệm, đăng ký với `name=alpha*` đã bị từ chối đúng như vậy.

`isRegistered(exactName)` kiểm tra một tên đã đăng ký. Để truy vấn theo pattern, hãy dùng `queryNames(pattern, null)`, không dùng `isRegistered(pattern)` như thay thế.

### 7.4. Canonical name giúp so và log

`ObjectName.getCanonicalName()` sắp xếp key properties theo tên khóa trong biểu diễn canonical:

```text
Input:     com.example.jmx:type=Cache,name=alpha1,region=eu
Canonical: com.example.jmx:name=alpha1,region=eu,type=Cache
```

Equality của ObjectName không phụ thuộc thứ tự keys. Tránh tự so các chuỗi trước và sau khi thay đổi property order; dùng `ObjectName.equals` hoặc canonical form.

## 8. Đăng ký MXBean mà vẫn giữ ObjectName đúng

Trong JMX, có thể tạo một MXBean bằng class implements management interface rồi wrap:

```java
StandardMBean mx = new StandardMBean(
        new CacheStats(11),
        CacheStatsMXBean.class,
        true);

ObjectName name = new ObjectName(
        "com.example.jmx:type=Cache,name=alpha1,region=eu");

server.registerMBean(mx, name);
```

Đây là **mảnh code trong ngữ cảnh class cụ thể**; chương trình độc lập ở phần tiếp theo có `CacheStats`, `CacheStatsMXBean`, `server`, imports và lifecycle đầy đủ.

Điểm cốt lõi:

- `true` trong `StandardMBean(..., true)` biểu thị interface dùng quy tắc **MXBean**, không phải Standard MBean.
- `name` cần **không phải pattern**.
- `getAttribute(name,"HitCount")` đọc management attribute từ getter `getHitCount()`.
- `JMX.newMXBeanProxy(connection, name, CacheStatsMXBean.class)` cho phép truy cập theo interface MXBean.
- Naming và matching của `ObjectName` độc lập với cơ chế Open Type mapping của MXBean.
- Hủy đăng ký bằng `unregisterMBean(name)` khi vòng đời object kết thúc; tránh registry stale và name collision.

## 9. Chương trình Java 17+ hoàn chỉnh: ObjectNameWildcardDemo.java

Chương trình tạo một **MBeanServer riêng trong tiến trình**, đăng ký 9 cache-statistics MXBeans. Mọi ví dụ miền `com.example.jmx` đều là dữ liệu test; không kết nối đến domain thật hoặc mở JMX remote.

Dữ liệu gồm:

| Tên giá trị | Kiểu serialization | Region | Vai trò |
| --- | --- | --- | --- |
| `alpha` | Unquoted | `eu` | Chứng minh `*` khớp cả suffix rỗng. |
| `alpha1` | Unquoted | `eu` | Chứng minh `?` khớp một ký tự. |
| `alpha2` | Unquoted | `us` | Chứng minh wildcard xuyên nhiều region. |
| `beta` | Unquoted | `eu` | Negative match. |
| `alpha zone` | Quoted | `us` | Giá trị có dấu cách. |
| `alpha*literal` | Quoted, escaped `*` | `eu` | Wildcard literal cần quote. |
| `alpha?literal` | Quoted, escaped `?` | `us` | Wildcard literal cần quote. |
| `alphaX` | Quoted | `eu` | `?` trong quoted pattern khớp một ký tự. |
| `sales,west=1` | Quoted | `ap` | Không cho dấu phẩy tạo property mới. |

### 9.1. Source đầy đủ

**Lưu UTF-8 thành file `ObjectNameWildcardDemo.java`:**

```java
import javax.management.JMX;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import javax.management.RuntimeOperationsException;
import javax.management.StandardMBean;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public final class ObjectNameWildcardDemo {
    public interface CacheStatsMXBean {
        long getHitCount();
        String getState();
    }
    public static final class CacheStats implements CacheStatsMXBean {
        private final long hitCount;
        CacheStats(long hitCount) { this.hitCount = hitCount; }
        @Override public long getHitCount() { return hitCount; }
        @Override public String getState() { return "READY"; }
    }

    private static final String DOMAIN = "com.example.jmx";
    private static int passed;

    private static void check(String label, boolean actual) {
        if (!actual) throw new AssertionError(label);
        passed++;
        System.out.println(label + "=PASS");
    }
    private static ObjectName name(String rawValue, String region,
                                   boolean quote) throws Exception {
        String safeValue = quote ? ObjectName.quote(rawValue) : rawValue;
        ObjectName n = new ObjectName(DOMAIN + ":type=Cache,name="
                + safeValue + ",region=" + region);
        if (n.isPattern()) {
            throw new IllegalArgumentException(
                    "Registration name must be exact");
        }
        return n;
    }
    private static ObjectName register(
            MBeanServer server, List<ObjectName> names,
            String rawValue, String region, boolean quote, long hits)
            throws Exception {
        ObjectName n = name(rawValue, region, quote);
        server.registerMBean(new StandardMBean(
                new CacheStats(hits), CacheStatsMXBean.class, true), n);
        names.add(n);
        return n;
    }
    private static Set<ObjectName> query(
            MBeanServer server, String pattern) throws Exception {
        return server.queryNames(new ObjectName(pattern), null);
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = MBeanServerFactory.createMBeanServer();
        List<ObjectName> names = new ArrayList<>();
        try {
            ObjectName alpha = register(
                    server, names, "alpha", "eu", false, 10);
            ObjectName alpha1 = register(
                    server, names, "alpha1", "eu", false, 11);
            ObjectName alpha2 = register(
                    server, names, "alpha2", "us", false, 12);
            register(server, names, "beta", "eu", false, 20);
            ObjectName space = register(
                    server, names, "alpha zone", "us", true, 30);
            ObjectName literalStar = register(
                    server, names, "alpha*literal", "eu", true, 40);
            ObjectName literalQuestion = register(
                    server, names, "alpha?literal", "us", true, 50);
            ObjectName quotedOneChar = register(
                    server, names, "alphaX", "eu", true, 60);
            ObjectName commaValue = register(
                    server, names, "sales,west=1", "ap", true, 70);

            check("registeredNineExact", names.size() == 9
                    && names.stream().allMatch(server::isRegistered)
                    && names.stream().noneMatch(ObjectName::isPattern));

            check("mxbeanAttribute", Long.valueOf(11L).equals(
                    server.getAttribute(alpha1, "HitCount")));
            check("mxbeanProxy", JMX.newMXBeanProxy(
                    server, alpha2, CacheStatsMXBean.class)
                    .getState().equals("READY"));

            ObjectName reordered = new ObjectName(
                    DOMAIN + ":region=eu,name=alpha1,type=Cache");
            check("canonicalOrderEquals", alpha1.equals(reordered)
                    && alpha1.getCanonicalName().equals(
                    reordered.getCanonicalName()));

            String base = DOMAIN + ":type=Cache,name=";
            ObjectName withoutExtraKeys = new ObjectName(base + "alpha*");
            ObjectName withExtraKeys = new ObjectName(base + "alpha*,*");

            check("valuePatternFlag",
                    withExtraKeys.isPattern()
                    && withExtraKeys.isPropertyValuePattern()
                    && withExtraKeys.isPropertyValuePattern("name")
                    && !withExtraKeys.isPropertyValuePattern("type"));
            check("listPatternFlag",
                    !withoutExtraKeys.isPropertyListPattern()
                    && withExtraKeys.isPropertyListPattern());
            check("noListWildcardRequiresExactKeys",
                    query(server, base + "alpha*").isEmpty());

            Set<ObjectName> prefix = query(server, base + "alpha*,*");
            check("unquotedStarPrefixThree",
                    prefix.size() == 3
                    && prefix.contains(alpha)
                    && prefix.contains(alpha1)
                    && prefix.contains(alpha2));
            check("unquotedQuestionOneCharacter",
                    query(server, base + "alpha?,*").size() == 2);
            check("unquotedRegionEuTwo",
                    query(server, base + "alpha*,region=eu").size() == 2);
            check("wildcardRegionOneCharacter",
                    query(server, base + "alpha*,region=e?").size() == 2);

            ObjectName quotedWildcard =
                    new ObjectName(base + "\"alpha*\",*");
            Set<ObjectName> quotedMatches =
                    server.queryNames(quotedWildcard, null);
            check("quotedStarStillPattern",
                    quotedWildcard.isPropertyValuePattern("name"));
            check("quotedWildcardMatchesFourQuoted",
                    quotedMatches.size() == 4
                    && quotedMatches.contains(space)
                    && quotedMatches.contains(literalStar)
                    && quotedMatches.contains(literalQuestion)
                    && quotedMatches.contains(quotedOneChar));
            check("quotedPatternDoesNotMatchUnquoted",
                    !quotedMatches.contains(alpha)
                    && !quotedMatches.contains(alpha1));
            check("quotedQuestionMatchesOneQuoted",
                    query(server, base + "\"alpha?\",*")
                    .equals(Set.of(quotedOneChar)));

            check("quoteEscapesLiteralStar",
                    !literalStar.isPattern()
                    && server.isRegistered(literalStar)
                    && ObjectName.quote("alpha*literal")
                    .equals(literalStar.getKeyProperty("name")));
            check("quoteEscapesLiteralQuestion",
                    !literalQuestion.isPattern()
                    && server.isRegistered(literalQuestion));
            check("unquoteRoundTrip",
                    ObjectName.unquote(literalStar.getKeyProperty("name"))
                    .equals("alpha*literal"));
            check("unquotedStarWouldBePattern",
                    new ObjectName(base + "alpha*literal,region=eu")
                    .isPropertyValuePattern("name"));

            String unusual = "r,=:\\\"*?\n";
            ObjectName safeUnusual = name(unusual, "test", true);
            check("quoteProtectsSpecialCharacters",
                    !safeUnusual.isPattern()
                    && ObjectName.unquote(
                            safeUnusual.getKeyProperty("name"))
                    .equals(unusual));

            ObjectName injected = new ObjectName(
                    DOMAIN + ":type=Cache,name=sales,west=1,region=ap");
            check("rawCommaChangesKeySet",
                    injected.getKeyPropertyList().size() == 4
                    && "sales".equals(injected.getKeyProperty("name"))
                    && "1".equals(injected.getKeyProperty("west")));
            check("quotedCommaKeepsThreeKeys",
                    commaValue.getKeyPropertyList().size() == 3
                    && "sales,west=1".equals(ObjectName.unquote(
                    commaValue.getKeyProperty("name"))));

            check("domainWildcardMatchesNine",
                    query(server, "com.example.*:type=Cache,*").size() == 9);
            check("caseSensitiveNoMatch",
                    query(server, base + "ALPHA*,*").isEmpty());
            check("propertyListWildcardMatchesNine",
                    query(server, DOMAIN + ":type=Cache,*").size() == 9);

            boolean rejected = false;
            try {
                server.registerMBean(new StandardMBean(
                        new CacheStats(0), CacheStatsMXBean.class, true),
                        new ObjectName(base + "alpha*,region=eu"));
            } catch (RuntimeOperationsException expected) {
                rejected = true;
            }
            check("patternCannotBeRegistrationName", rejected);
            check("patternApplyMatchesOnlyNonPattern",
                    withExtraKeys.apply(alpha1)
                    && !withExtraKeys.apply(literalStar)
                    && !withExtraKeys.apply(withExtraKeys));
            check("canonicalNameSorted",
                    alpha1.getCanonicalName().equals(
                    DOMAIN + ":name=alpha1,region=eu,type=Cache"));

            final int expected = 28;
            if (passed != expected) {
                throw new AssertionError("Expected " + expected
                        + " tests, got " + passed);
            }
            System.out.println("checks=" + passed + "/" + expected);
        } finally {
            for (ObjectName n : names) {
                if (server.isRegistered(n)) {
                    server.unregisterMBean(n);
                }
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

**Giải thích code:** `name(...)` cố ý có tham số `quote` để tạo hai nhóm tên phục vụ bài test. **Trong ứng dụng nhận input động, dùng `ObjectName.quote(rawValue)` cho mọi value lấy từ dữ liệu**, không dùng `quote=false` với user input. Giá trị `quote=false` trong demo chỉ áp dụng các chuỗi test literal đã biết từ source code.

Chương trình dùng `StandardMBean(...,true)` để MXBean được nhận diện rõ; `MBeanServerFactory.createMBeanServer()` tạo server JMX cục bộ riêng, khác với việc bật remote JMX agent. `finally` hủy các registrations đã tạo và release server.

### 9.2. Biên dịch và chạy

Yêu cầu JDK 17 trở lên; trong terminal tại thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 ObjectNameWildcardDemo.java
java ObjectNameWildcardDemo
```

`javax.management` nằm trong module chuẩn **`java.management`** của Java. Với source chạy theo classpath như trên không cần Maven/Gradle, thư viện ngoài hay `--add-exports`. Khi dùng **named module** với `module-info.java`, khai báo `requires java.management;`.

### 9.3. Stdout chính xác đã kiểm chứng

```text
registeredNineExact=PASS
mxbeanAttribute=PASS
mxbeanProxy=PASS
canonicalOrderEquals=PASS
valuePatternFlag=PASS
listPatternFlag=PASS
noListWildcardRequiresExactKeys=PASS
unquotedStarPrefixThree=PASS
unquotedQuestionOneCharacter=PASS
unquotedRegionEuTwo=PASS
wildcardRegionOneCharacter=PASS
quotedStarStillPattern=PASS
quotedWildcardMatchesFourQuoted=PASS
quotedPatternDoesNotMatchUnquoted=PASS
quotedQuestionMatchesOneQuoted=PASS
quoteEscapesLiteralStar=PASS
quoteEscapesLiteralQuestion=PASS
unquoteRoundTrip=PASS
unquotedStarWouldBePattern=PASS
quoteProtectsSpecialCharacters=PASS
rawCommaChangesKeySet=PASS
quotedCommaKeepsThreeKeys=PASS
domainWildcardMatchesNine=PASS
caseSensitiveNoMatch=PASS
propertyListWildcardMatchesNine=PASS
patternCannotBeRegistrationName=PASS
patternApplyMatchesOnlyNonPattern=PASS
canonicalNameSorted=PASS
checks=28/28
```

Có **28 kết quả PASS và một dòng tổng kết**, hoàn toàn deterministic vì chỉ in nhãn kiểm tra, không in thông tin MBeanServer delegate hoặc thứ tự lặp ngẫu nhiên của Set. Toàn bộ chương trình đã biên dịch bằng `--release 17` và chạy thành công trong môi trường JDK có sẵn, không sử dụng JMX remote connector.

## 10. Hiểu kết quả kiểm thử theo từng nhóm

### 10.1. MXBean có tên thực và gọi được

- `registeredNineExact` kiểm tra đã tạo đủ 9 MBeans, cả 9 ObjectName **không phải pattern** và đều được đăng ký.
- `mxbeanAttribute` đọc `HitCount=11` từ `getHitCount()` qua JMX.
- `mxbeanProxy` dùng typed proxy và kiểm tra trạng thái `READY`.
- `canonicalOrderEquals` khẳng định `region=eu,name=alpha1,type=Cache` bằng tên có các properties đảo thứ tự.

### 10.2. Property-value wildcard vs property-list wildcard

- `valuePatternFlag`: `name=alpha*` được nhận diện là value pattern, `type=Cache` thì không.
- `listPatternFlag`: thêm `,*` làm `isPropertyListPattern()` thành true.
- `noListWildcardRequiresExactKeys`: query thiếu `region` và thiếu list wildcard không match, kết quả rỗng.
- `unquotedStarPrefixThree`: với `,*`, prefix `alpha*` tìm đủ `alpha`, `alpha1`, `alpha2`; ngôi `alpha` chứng minh wildcard `*` có thể khớp **zero characters**.
- `unquotedQuestionOneCharacter`: `alpha?` chỉ khớp `alpha1` và `alpha2`.
- `unquotedRegionEuTwo`: `alpha*` kết hợp `region=eu` chỉ tìm `alpha` và `alpha1`.
- `wildcardRegionOneCharacter`: `region=e?` khớp `eu` nhưng không khớp `us`.

### 10.3. Quoted wildcard không bị tắt

- `quotedStarStillPattern` xác nhận `name="alpha*"` vẫn là value pattern.
- `quotedWildcardMatchesFourQuoted`: truy vấn quoted form tìm `alpha zone`, `alpha*literal`, `alpha?literal` và `alphaX` đã được đăng ký bằng quoted representation.
- `quotedPatternDoesNotMatchUnquoted`: quoted query không tìm `alpha`/`alpha1` unquoted.
- `quotedQuestionMatchesOneQuoted`: quoted `name="alpha?"` chỉ tìm tên `"alphaX"`.

Đây là minh họa đã được kiểm chứng trên JDK: **quotes không thay thế escape**, và matching có thể khác khi registry trộn quoted/unquoted values.

### 10.4. Quoting literal values

- `quoteEscapesLiteralStar`: tên có raw `alpha*literal` được quote thành literal, không còn là pattern.
- `quoteEscapesLiteralQuestion`: tương tự với `alpha?literal`.
- `unquoteRoundTrip`: giải mã đúng về raw value.
- `unquotedStarWouldBePattern`: nếu viết raw `alpha*literal` vào ObjectName không quote, nó sẽ là pattern.
- `quoteProtectsSpecialCharacters`: cả punctuation, backslash, quotes, wildcard, newline đều được quote/unquote chính xác.

### 10.5. An toàn cấu trúc tên

- `rawCommaChangesKeySet`: input `sales,west=1` ghép raw bị tách thành **hai properties** `name=sales` và `west=1`.
- `quotedCommaKeepsThreeKeys`: dùng `ObjectName.quote` giữ nguyên giá trị `sales,west=1` và chỉ có ba keys như dự kiến.
- `patternCannotBeRegistrationName`: server từ chối register pattern ObjectName.
- `patternApplyMatchesOnlyNonPattern`: `apply` không coi một pattern khác như concrete MBean name.

### 10.6. Domain và canonicalization

- `domainWildcardMatchesNine` tìm đủ 9 MXBeans trong domain `com.example.*`.
- `caseSensitiveNoMatch` cho thấy `ALPHA*` không khớp `alpha...`.
- `propertyListWildcardMatchesNine` truy vấn toàn bộ Cache MXBeans trong domain bằng `type=Cache,*`.
- `canonicalNameSorted` xác nhận biểu diễn canonical sắp keys theo thứ tự từ điển.

## 11. Các lỗi dễ gặp trong ứng dụng MXBean thật

| Sai lầm | Biểu hiện | Cách sửa |
| --- | --- | --- |
| Tạo tên từ `name=alpha*literal` để đăng ký. | `isPattern()==true`, không đăng ký được như một tên cụ thể. | `ObjectName.quote("alpha*literal")`. |
| Chỉ thêm dấu nháy `name="alpha*"`. | Vẫn là wildcard pattern. | Escape `*` thành literal bằng `quote`. |
| Ghép raw tên chứa `,` hoặc `=`. | Thêm/sửa key properties ngoài dự kiến. | Quote raw string values; validate key schema. |
| Nghĩ `name=alpha*` cũng cho phép thêm `region`. | `queryNames` trả rỗng dù có names matching prefix. | Thêm `,*` hoặc liệt kê đủ keys. |
| Nhầm `name=*` với `,*`. | Query trả kết quả khác. | Phân biệt value wildcard và property-list wildcard. |
| Viết `name=alpha\*literal` không quote. | Không đạt literal escaping như ý. | Sử dụng quoted value qua `ObjectName.quote`. |
| Đăng ký names lúc quote lúc không quote. | Query prefix chỉ tìm một nhóm. | Quy ước serialization nhất quán. |
| Dùng `ObjectName.quote(prefix + "*")` để search. | Wildcard được escape, trở thành literal. | Xây pattern có chủ đích, test riêng. |
| Coi wildcard là regex `alpha.*`. | JMX glob semantics khác regex. | `*` cho chuỗi bất kỳ, `?` cho một ký tự. |
| Đặt `*` trong key name `na*=...`. | Không phải cú pháp hợp lệ. | Chỉ pattern domain/value/list. |
| Tự so tên bằng raw String với property order khác. | Báo sai khác. | ObjectName equality/canonical form. |
| Cho rằng Set kết quả query có thứ tự ổn định. | Output/test flaky. | Sort canonical names nếu cần hiển thị. |
| Dùng `isRegistered(pattern)` để tìm nhiều beans. | Không có semantics truy vấn như mong muốn. | `queryNames(pattern,null)`. |
| Nhầm ObjectName pattern với Java `Pattern` regex. | Query không khớp/khớp quá nhiều. | Dùng chính xác JMX ObjectName syntax. |
| Dùng tên có wildcard để authorize dữ liệu tenant. | Có thể match MBeans ngoài tenant. | AuthN/AuthZ độc lập, enforce scope. |
| Bật remote JMX không có xác thực/TLS. | Lộ thông tin vận hành, có thể có operations nhạy cảm. | Giới hạn network, authentication, TLS và quyền. |
| Không unregister MBeans. | Registry stale, trùng tên hoặc memory pressure. | Vòng đời registration và cleanup rõ ràng. |
| Đặt domain tên chung `default` trong nhiều thư viện. | Dễ va chạm tên. | Reverse-DNS domain theo owner. |
| Log user input đã chứa credentials trong ObjectName. | Dữ liệu nhạy cảm bị lộ qua JMX/listing. | Không đưa secrets/PII vào MXBean names. |

## 12. Xây tên động an toàn và có thể truy vấn lâu dài

### 12.1. Định nghĩa schema tên rõ ràng

Ví dụ một naming convention:

```text
com.example.jmx:type=Cache,name="raw-id",region=us
```

Mỗi instance có đúng ba keys: `type`, `name`, `region`. Tất cả `name` từ dữ liệu được quote, kể cả khi nó không có ký tự đặc biệt. `region` nên đến từ một allowlist nội bộ hoặc cũng được quote nếu lấy từ dữ liệu không tin cậy.

Mẫu:

```java
String rawId = externalName;
String safeName = ObjectName.quote(rawId);
String safeRegion = ObjectName.quote(region);

ObjectName exact = new ObjectName(
        "com.example.jmx:type=Cache,name="
        + safeName + ",region=" + safeRegion);

if (exact.isPattern()) {
    throw new IllegalStateException(
            "Registration ObjectName must not be a pattern");
}
```

Đây là đoạn minh họa yêu cầu `externalName`/`region` có giá trị và imports phù hợp; không phải Java file độc lập. Khi bạn **quote cả region**, query pattern cũng phải áp quy tắc matching tương thích với quoted values.

### 12.2. Không lẫn raw value và pattern text

Hai loại dữ liệu nên được đặt tên khác nhau trong code:

- `rawName`: tên người dùng/instance, **literal**, phải quote.
- `queryPattern`: mẫu tìm kiếm **được code tin cậy thiết kế**, có `*`/`?` cố ý.
- `exactObjectName`: phải `!isPattern()` để register, getAttribute theo một MBean.
- `objectNamePattern`: dùng `queryNames`, không register.

Nếu cho end-user điều khiển wildcard trong query, áp allowlist/quotas để hạn chế matching scope và số results. Không đưa wildcard parser trực tiếp ra một API quản trị mà thiếu auth.

### 12.3. Không tự tạo namespace phân quyền chỉ bằng domain

Domain và key properties là **tên định danh**, không phải một sandbox. Một query `*:type=Cache,*` có thể tìm nhiều MBeans nếu caller có khả năng xem registry. Bảo mật remote JMX bằng authenticated connector, transport protection, access controls và giới hạn exposure; kiểm tra quyền tenant/resource ở tầng application. Không đặt password, token hoặc dữ liệu khách hàng vào `ObjectName`.

### 12.4. Đừng đổi naming format âm thầm

Nếu phiên bản cũ đăng ký unquoted `name=alpha1`, bản mới quote `name="alpha1"`, **đó có thể là hai ObjectNames khác nhau**. Các scripts và monitoring queries cũ có thể không còn match.

Khi migrate:
1. Kiểm kê naming conventions.
2. Lưu lại các query patterns đang dùng.
3. Chọn canonical schema và quoting policy mới.
4. Test queries trên hỗn hợp old/new registrations.
5. Thực hiện migration/alias nếu cần và có rollback.
6. Cập nhật dashboard/alert filters.
7. Không đổi lén key names hoặc quotes rồi nghĩ ObjectName equality vẫn y như cũ.

## 13. An toàn JMX và hiệu năng truy vấn

### 13.1. queryNames trả metadata, không bảo đảm permission

`MBeanServer.queryNames(pattern,null)` là API truy vấn tên trong server được cấp quyền tương ứng. Việc pattern chứa `tenant=abc` hoặc `name=abc*` không tự xác minh user đang truy vấn có được phép xem tenant ABC hay không. Với management console/service:

- Bảo vệ kết nối remote JMX và credentials.
- Không bật remote connector mở ra Internet không có authentication/TLS.
- Áp access control phù hợp cho attributes và operations.
- Không để người dùng nhập `*:*` tùy ý nếu không có quyền quản trị toàn cục.
- Không chứa secrets/PII trong ObjectNames hoặc metric names.
- Log/monitor truy vấn quá rộng hoặc quá thường xuyên; tránh enumerate hàng nghìn MBeans mỗi request.
- Với multi-tenant, kiểm tra quyền thực ở service trước/ngoài matching.

### 13.2. queryNames không phải indexing query engine

JMX `ObjectName` pattern là công cụ **khám phá MBeans** theo naming scheme, không thay database, search engine hoặc authorization engine. Với số lượng lớn registrations:

- Dùng domain/namespaces hẹp trước.
- Gắn đúng exact properties hoặc pattern ngắn thay vì `*:*`.
- Giới hạn tần suất, số lượng kết quả và thời gian truy vấn theo khả năng service.
- Lưu cached names cẩn thận vì registrations có thể đến/đi.
- Không dùng kết quả query của một thời điểm để suy kết toàn bộ trạng thái hệ thống khi MBeans đăng ký/hủy liên tục.

### 13.3. Một local MBeanServer không tự mở JMX TCP port

Demo tạo `MBeanServerFactory.createMBeanServer()`, đăng ký các MXBeans **trong cùng JVM** rồi giải phóng khi xong. Nó không tạo một JMX remote connector. Nếu ứng dụng chủ động dùng remote monitoring, đó là bước cấu hình riêng với trust/auth/access policy. Không kết luận “mọi MXBean đều tự public qua mạng” chỉ vì có ObjectName.

## 14. Bảng kiểm tra trước khi đăng ký và truy vấn

- [ ] Domain đã theo naming convention thống nhất (ưu tiên reverse-DNS)?
- [ ] Tất cả keys không rỗng và không chứa ký tự cấm?
- [ ] Không có duplicate property keys?
- [ ] Raw dynamic values được đưa qua `ObjectName.quote`?
- [ ] `ObjectName.isPattern()` là false trước `registerMBean`?
- [ ] Tên có literal `*`/`?` không bị hiểu thành wildcard?
- [ ] Chuỗi có dấu phẩy, dấu bằng hoặc newline được quote đúng?
- [ ] Có xử lý `MalformedObjectNameException`/`RuntimeOperationsException` hợp lý?
- [ ] Có phân biệt `name=*` với `,*`?
- [ ] Nếu đăng ký thêm `region`/`tenant`, query có liệt kê key hoặc `,*`?
- [ ] Query dùng wildcard `*` và `?` đúng semantics (không phải regex)?
- [ ] Query quoted/unquoted phù hợp naming convention của registry?
- [ ] Đã test `name="alpha*"` vẫn là pattern khi `*` không escape?
- [ ] Có kiểm tra `isPropertyValuePattern("name")` khi debug?
- [ ] Không dùng `isRegistered(pattern)` thay `queryNames`?
- [ ] Không dựa vào thứ tự iteration của `Set<ObjectName>`?
- [ ] Đã dùng `ObjectName.equals`/`getCanonicalName` thay tự so raw strings?
- [ ] Có lifecycle `unregisterMBean` khi instance kết thúc?
- [ ] Có giới hạn query scope, quyền remote JMX, số results?
- [ ] Không để user-supplied wildcard trở thành wildcard query ngoài ý muốn?
- [ ] Không đặt mật khẩu, token, PII hoặc tenant secrets trong name?
- [ ] Có tests thực tế với cả quoted và unquoted names?
- [ ] Có đo và giới hạn tác động monitoring wildcard query lên ứng dụng?

## 15. Bài tập thực hành

**A — Wildcard rỗng.** Đăng ký `name=alpha`, `alpha1` và `alpha2`, rồi truy vấn `name=alpha*,*`. Giải thích vì sao `alpha` cũng khớp.

**B — Một ký tự.** Đổi pattern `name=alpha*` thành `name=alpha?` và quan sát số lượng. So sánh `alpha` với `alpha2` và `alpha-long`.

**C — Quoted không tắt wildcard.** Tạo `new ObjectName("d:name=\"foo*\"")`, gọi `isPropertyValuePattern("name")`. Tại sao nó vẫn true?

**D — Escape literal.** Dùng `ObjectName.quote("foo*bar")` và `ObjectName.quote("foo?bar")`; khẳng định `isPattern() == false` khi tạo tên đầy đủ.

**E — List wildcard.** Có `d:type=Cache,name=a,region=eu`. So sánh `queryNames` với `d:type=Cache,name=a*` và `d:type=Cache,name=a*,*`.

**F — Quotes và representation.** Tạo một tên bằng raw `name=alpha1` và một tên bằng `ObjectName.quote("alpha1")`. Chứng minh hai representations khác nhau và thiết kế query tương ứng.

**G — Dấu phẩy trong dữ liệu.** Với `name=sales,west=1`, đếm keys trước/sau khi quote; vì sao không thể chỉ dựa vào việc constructor không throw exception?

**H — Key wildcards.** Thử tên `d:na*=foo` và tìm exception; phân biệt key wildcard không hợp lệ với value wildcard.

**I — Canonical form.** Hoán vị ba keys `name`, `region`, `type` và so equality, `getCanonicalName()`.

**J — Apply.** Thử `ObjectName.apply` với exact ObjectName và với một pattern ObjectName khác, phân tích kết quả false cho pattern target.

**K — MXBean attribute.** Thêm getter `getMissCount()` và kiểm tra `MBeanServer.getAttribute`/`JMX.newMXBeanProxy` trên một tên exact.

**L — Query an toàn.** Thiết kế REST endpoint quản trị nhận `namePrefix` từ user. Phân tách raw literal prefix, pattern do ứng dụng cho phép, authZ và max-results, tránh gửi thẳng string đầu vào tới `new ObjectName`.

**M — Case sensitivity.** Truy vấn `name=ALPHA*,*` khi registry chỉ có `alpha...`; kết quả thế nào?

**N — Domain patterns.** Thêm một domain `com.example.other` và so `com.example.*:type=Cache,*` với domain exact.

**O — Migration.** Thiết kế kế hoạch chuyển from unquoted names to consistently quoted names mà monitoring dashboards/alerts không mất dữ liệu.

## 16. Câu hỏi tự kiểm tra

**1. ObjectName có thể là tên cụ thể và pattern không?** — Có. Phân biệt bằng `isPattern()`.

**2. Hai ký tự wildcard property value là gì?** — `*` cho 0 hoặc nhiều ký tự, `?` cho đúng một ký tự.

**3. `name="foo*"` có tự biến `*` thành literal không?** — Không, wildcard chưa escape vẫn là pattern.

**4. Cách đúng để giữ raw value `foo*bar`?** — `ObjectName.quote("foo*bar")`.

**5. Có thể dùng `name=foo\*bar` không quote để escape không?** — Không nên. Quy tắc escaping wildcard là bên trong quoted value; dùng `quote`.

**6. Khác nhau giữa `name=*` và `,*`?** — Cái đầu wildcard giá trị key `name`, cái sau cho phép thêm những key properties khác.

**7. Vì sao `name=alpha*` query có thể rỗng dù tồn tại `name=alpha1,region=eu`?** — Nếu query thiếu `region` và không có property-list wildcard `,*` thì không match key set.

**8. `name=alpha?` có match `alpha` không?** — Không; `?` cần đúng một ký tự.

**9. Quoted và unquoted patterns luôn match như nhau?** — Không. Representation quotes/backslashes của ObjectName có tác động.

**10. MBeanServer.registerMBean có đăng ký với wildcard name được không?** — Không. Cần exact ObjectName, không phải pattern.

**11. MBeanServer.queryNames trả kiểu gì?** — `Set<ObjectName>`; không bảo đảm iteration order.

**12. Dùng isRegistered(pattern) để tìm nhiều MBeans được không?** — Không; dùng `queryNames`.

**13. Có wildcard trong key names không?** — Không, `*` và `?` bị cấm ở key name.

**14. ObjectName.quote bảo vệ gì ngoài * và ??** — Quotes, backslashes, newline, dấu phẩy/dấu bằng để raw value không làm sai cấu trúc.

**15. getKeyProperty trả về raw string sau unescape không?** — Với quoted value, representation có quotes/backslashes; dùng `ObjectName.unquote` đúng điều kiện.

**16. CanonicalName dùng để làm gì?** — Biểu diễn key properties theo thứ tự cố định, so/log/debug thuận tiện.

**17. Wildcard query có là kiểm tra quyền tenant không?** — Không, JMX authorization phải được bảo vệ riêng.

**18. Có cần bật remote JMX để chạy demo không?** — Không, demo dùng local `MBeanServer`.

**19. Java test dùng external library không?** — Không, chỉ dùng module chuẩn `java.management`.

**20. Bài demo đã kiểm chứng bao nhiêu điều kiện?** — **28/28 PASS**, biên dịch `javac --release 17` và chạy bằng Java trong môi trường làm việc.

## 17. Tài liệu tham khảo chính thức, còn áp dụng

- [ObjectName — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/ObjectName.html): cú pháp domain/keys/values, wildcard `*`/`?`, quoted escapes, `isPropertyValuePattern`, `isPropertyListPattern`, `apply`, `quote` và `unquote`.
- [MBeanServer — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServer.html): `registerMBean`, `queryNames`, `isRegistered`, `getAttribute`, `unregisterMBean`.
- [MBeanServerFactory — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServerFactory.html): tạo/release local MBeanServer.
- [StandardMBean — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/StandardMBean.html): overload `StandardMBean(implementation, interface, true)` dùng cho MXBean.
- [JMX — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/JMX.html): `newMXBeanProxy` và các tiện ích JMX.
- [MXBean — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MXBean.html): interface MXBean và typing.
- [ObjectName — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/ObjectName.html): API tương thích với `--release 17` của chương trình.
- [Oracle — JMX Best Practices](https://www.oracle.com/java/technologies/javase/management-extensions-best-practices.html): conventions, case sensitivity, quoting và key order.
- [Oracle — Java Management Extensions Guide](https://docs.oracle.com/en/java/javase/26/management/java-management-extensions-jmx.html): tham khảo quản trị JMX trên Java hiện hành nếu có tài liệu tương ứng cho bản triển khai.

**Ghi nhớ:** `ObjectName` không chỉ là chuỗi định danh, nó còn có thể mang ý nghĩa **pattern**. Trong **giá trị khóa**, `*`/`?` là wildcard; dấu nháy kép không tự làm chúng thành literal. Dùng **`ObjectName.quote(raw)` để tạo tên đăng ký từ dữ liệu thật**, kiểm tra `!isPattern()`, phân biệt wildcard của **giá trị** và wildcard của **danh sách properties** `,*`, rồi dùng `queryNames` với pattern được xây dựng có chủ đích. Với MXBean, quản lý registration lifecycle và quyền truy cập JMX độc lập khỏi wildcard matching.

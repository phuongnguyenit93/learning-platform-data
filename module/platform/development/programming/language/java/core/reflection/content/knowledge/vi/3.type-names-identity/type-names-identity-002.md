# Tên nhị phân của lớp thành viên, lớp cục bộ và lớp vô danh trong Java

Khi làm việc với Java Reflection, một kiểu có thể được gọi bằng nhiều tên khác nhau: tên viết trong mã nguồn, **tên nhị phân (binary name)** dùng để định danh lớp sau khi biên dịch, tên đơn giản và tên chuẩn tắc. Với lớp lồng nhau, đặc biệt lớp cục bộ và lớp vô danh, các tên này khác nhau rõ rệt. Hiểu đúng chúng giúp đọc kết quả của `Class.getName()`, nạp lớp bằng `Class.forName(...)` và phân tích thông tin về lớp chứa.

## 1. Phân biệt ba loại lớp

- **Lớp thành viên (member class):** khai báo trực tiếp trong thân một lớp hoặc interface và có tên riêng. Có lớp thành viên `static` và lớp thành viên không `static` (inner class). Ví dụ `Outer.Member`. Tính `static` ảnh hưởng cách tạo đối tượng và khả năng truy cập đối tượng bao ngoài, nhưng cả hai trường hợp đều theo quy tắc tên nhị phân của member class.
- **Lớp cục bộ (local class):** lớp có tên, khai báo trong một khối, chẳng hạn bên trong phương thức, constructor hoặc khối khởi tạo. Ví dụ `class Local {}` bên trong phương thức `run()`. Tên `Local` chỉ có phạm vi sử dụng theo quy tắc Java tại nơi khai báo.
- **Lớp vô danh (anonymous class):** lớp khai báo tại biểu thức tạo đối tượng, chẳng hạn `new Runnable() { public void run() {} }`. Không có tên đơn giản do lập trình viên đặt và không có tên chuẩn tắc.

Một lớp mức trên cùng (top-level class) như `example.Outer` không thuộc ba loại trên. Biểu thức lambda cũng **không đồng nghĩa** với anonymous class trong mã nguồn: không nên áp quy tắc tên nhị phân của anonymous class cho những lớp triển khai lambda do JVM tạo.

## 2. Quy tắc tên nhị phân

Giả sử lớp bao ngoài có tên nhị phân `example.Outer`:

| Kiểu khai báo | Cách gọi ở mức mã nguồn | Dạng tên nhị phân minh họa |
| --- | --- | --- |
| Lớp mức trên cùng | `example.Outer` | `example.Outer` |
| Lớp thành viên `Member` | `Outer.Member` | `example.Outer$Member` |
| Lớp cục bộ `Local` trong `Outer` | `Local` tại phạm vi cục bộ | `example.Outer$1Local` |
| Lớp vô danh bên trong `Outer` | Không có tên kiểu trực tiếp | `example.Outer$1` |

Với **member class**, tên nhị phân là tên nhị phân của lớp/interface khai báo trực tiếp, dấu `$`, rồi tên đơn giản của lớp thành viên. Ví dụ, nếu `Inner` khai báo trong `Outer.Member` thì có dạng `example.Outer$Member$Inner`.

Với **local class**, Java Language Specification quy định dạng tên nhị phân: tên nhị phân của lớp/interface bao quanh, dấu `$`, **một chuỗi chữ số không rỗng do trình biên dịch sinh ra**, rồi tên đơn giản của lớp cục bộ: `Outer$<digits>Local`.

Với **anonymous class**, cấu trúc tương tự nhưng **không có tên đơn giản sau các chữ số**: `Outer$<digits>`.

Các số `1`, `2`… trong bảng chỉ minh họa. **Không suy luận thứ tự khai báo, phương thức, số dòng hay danh tính lâu dài từ số hậu tố.** Cách đánh số cụ thể phụ thuộc trình biên dịch và cấu trúc mã nguồn; thêm hoặc chuyển vị trí một khai báo có thể đổi tên được sinh. Bản thân ký tự `$` hợp lệ trong Java identifier, nên không được tách chuỗi tại mọi dấu `$` để khẳng định quan hệ chứa.

### Tên nhị phân và tên chuẩn tắc không giống nhau

- `Class.getName()` trả về tên nhị phân đối với lớp/interface thông thường, chẳng hạn `example.Outer$Member`. Với mảng, phương thức dùng dạng mã hóa riêng, trình bày ở phần 5.
- `Class.getSimpleName()` trả về `Member` với member class, `Local` với local class, và chuỗi rỗng `""` với anonymous class.
- `Class.getCanonicalName()` trả về `example.Outer.Member` cho member class có tên chuẩn tắc; trả về `null` cho local class và anonymous class. Một member class được khai báo bên trong kiểu vốn không có tên chuẩn tắc cũng có thể không có tên chuẩn tắc.
- `Class.getTypeName()` cung cấp biểu diễn tên kiểu dễ đọc, đặc biệt với mảng; không nên mặc định dùng nó như binary name để nạp lớp.

Dấu chấm trong `Outer.Member` thể hiện cú pháp tham chiếu kiểu/canonical name; dấu `$` trong `Outer$Member` thuộc binary name. Không được thay mọi dấu chấm bằng `$` vì dấu chấm phân cách tên package phải được giữ nguyên.

## 3. Ví dụ Java 17+ chạy được

Lưu mã thành **`BinaryNamesDemo.java`**. Ví dụ cố ý không in trực tiếp tên nhị phân của local class và anonymous class để kết quả không phụ thuộc các số do trình biên dịch sinh ra.

```java
public class BinaryNamesDemo {
    static class StaticMember {}
    class InnerMember {}

    static void inMethod() {
        class Local {}

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {}
        };

        describe("local", Local.class);
        describe("anonymous", anonymous.getClass());

        System.out.println("local enclosed by inMethod = "
                + Local.class.getEnclosingMethod().getName().equals("inMethod"));
        System.out.println("anonymous enclosed by inMethod = "
                + anonymous.getClass().getEnclosingMethod().getName().equals("inMethod"));
    }

    static void describe(String label, Class<?> type) {
        System.out.printf(
                "%s: simple='%s', canonical=%s, member=%s, local=%s, anonymous=%s%n",
                label, type.getSimpleName(), type.getCanonicalName(), type.isMemberClass(),
                type.isLocalClass(), type.isAnonymousClass());
    }

    public static void main(String[] args) throws ClassNotFoundException {
        describe("static-member", StaticMember.class);
        describe("inner-member", InnerMember.class);
        inMethod();

        System.out.println("binary member = " + StaticMember.class.getName());
        System.out.println("member loaded = "
                + (Class.forName("BinaryNamesDemo$StaticMember") == StaticMember.class));
    }
}
```

Biên dịch/chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 BinaryNamesDemo.java
java BinaryNamesDemo
```

Kết quả:

```text
static-member: simple='StaticMember', canonical=BinaryNamesDemo.StaticMember, member=true, local=false, anonymous=false
inner-member: simple='InnerMember', canonical=BinaryNamesDemo.InnerMember, member=true, local=false, anonymous=false
local: simple='Local', canonical=null, member=false, local=true, anonymous=false
anonymous: simple='', canonical=null, member=false, local=false, anonymous=true
local enclosed by inMethod = true
anonymous enclosed by inMethod = true
binary member = BinaryNamesDemo$StaticMember
member loaded = true
```

Giải thích:

1. `StaticMember` và `InnerMember` đều là **member class**, vì vậy `isMemberClass()` bằng `true`, bất kể khai báo `static` hay không.
2. `Local` có tên đơn giản là `Local` nhưng không có canonical name; `isLocalClass()` bằng `true`.
3. Đối tượng `anonymous` thuộc anonymous class; `getSimpleName()` trả chuỗi rỗng và `isAnonymousClass()` bằng `true`.
4. `getEnclosingMethod()` xác định vị trí khai báo bên trong phương thức `inMethod` mà không cần phân tích chuỗi tên.
5. `Class.forName("BinaryNamesDemo$StaticMember")` nhận **binary name** của member class; chuỗi `"BinaryNamesDemo.StaticMember"` không tìm được lớp tương ứng trong ví dụ.

Nếu in thêm `Local.class.getName()` hoặc `anonymous.getClass().getName()`, có thể thấy dạng `BinaryNamesDemo$1Local` và `BinaryNamesDemo$1`. Những số này là ví dụ, không phải stdout cố định cần ghi nhớ.

## 4. Nhận diện loại lớp bằng Reflection

Khi đã có `Class<?> type`, dùng các API thể hiện cấu trúc kiểu thay vì đoán từ tên:

| API | Member class | Local class | Anonymous class |
| --- | --- | --- | --- |
| `isMemberClass()` | `true` | `false` | `false` |
| `isLocalClass()` | `false` | `true` | `false` |
| `isAnonymousClass()` | `false` | `false` | `true` |
| `getDeclaringClass()` | Lớp/interface khai báo trực tiếp | `null` | `null` |
| `getEnclosingClass()` | Lớp chứa | Lớp bao quanh về mặt từ vựng | Lớp bao quanh về mặt từ vựng |
| `getEnclosingMethod()` | Thường `null` | Phương thức bao quanh, nếu khai báo trong phương thức | Phương thức bao quanh, nếu khai báo trong phương thức |

`getEnclosingConstructor()` trả về constructor bao quanh khi local/anonymous class được khai báo trong constructor. Trong initializer hoặc ngữ cảnh không thuộc thân method/constructor, cả `getEnclosingMethod()` và `getEnclosingConstructor()` có thể bằng `null`. Vì vậy hai giá trị `null` này không đủ để kết luận đó là member class.

Ví dụ kiểm tra khai báo chứa:

```java
Class<?> member = BinaryNamesDemo.StaticMember.class;
System.out.println(member.getDeclaringClass() == BinaryNamesDemo.class); // true
System.out.println(member.getEnclosingClass() == BinaryNamesDemo.class); // true
```

Đây là **đoạn mã minh họa bổ sung** chạy trong ngữ cảnh đã biên dịch `BinaryNamesDemo`, không phải một chương trình hoàn chỉnh độc lập.

Đối với debugger, tracer, hay công cụ phân tích metadata, nên dựa vào `isMemberClass()`, `isLocalClass()`, `isAnonymousClass()` cùng các API `getEnclosing...()`. Việc suy đoán dựa trên mẫu ký tự `$1` vừa dễ sai vừa nhạy cảm với thay đổi của compiler.

## 5. Nạp lớp và những trường hợp tên dễ nhầm

### Nạp lớp theo tên

`Class.forName(String)` cần binary name khi nạp một lớp thông thường:

```java
Class<?> type = Class.forName("BinaryNamesDemo$StaticMember");
System.out.println(type == BinaryNamesDemo.StaticMember.class); // true
```

Trong ví dụ, `BinaryNamesDemo` thuộc package mặc định nên tên không có tiền tố package. Nếu đặt trong `package example;`, tên nhị phân thành `example.BinaryNamesDemo$StaticMember`.

Với local và anonymous class, có thể lấy tên thực tế bằng `getName()` từ đối tượng `Class<?>`. Dù vậy, hard-code tên do compiler tự sinh rất dễ hỏng khi sửa mã. Khi nạp lớp trong ứng dụng thực tế còn cần xét **ClassLoader**: tên giống nhau nhưng hai class loader khác nhau có thể cho hai đối tượng `Class` khác nhau. `Class.forName(name)` có thể kích hoạt khởi tạo lớp; dạng `Class.forName(name, false, loader)` cho phép yêu cầu nạp mà không khởi tạo tại thời điểm đó.

### Tên của mảng

`Class.getName()` đối với mảng dùng biểu diễn riêng, không đơn thuần là tên nhị phân của lớp phần tử:

- `int[].class.getName()` trả `[I`.
- `String[].class.getName()` trả `[Ljava.lang.String;`.
- `BinaryNamesDemo.StaticMember[].class.getName()` trả `[LBinaryNamesDemo$StaticMember;`.
- Mảng hai chiều của member class bắt đầu bằng `[[L`.

Ở đây, mỗi `[` biểu thị một chiều; `L...;` biểu thị phần tử là kiểu tham chiếu; `I` biểu thị `int`. Vì thế chuỗi trả về từ `getName()` của mảng không phải trực tiếp binary name của một lớp thường.

### Tên tệp khi biên dịch

`javac` thường sinh `BinaryNamesDemo.class`, `BinaryNamesDemo$StaticMember.class` và các tệp riêng cho local/anonymous class. Các tên tệp đó có liên hệ với tên nhị phân, nhưng không được dựa vào hậu tố số trong tệp `.class` để suy diễn vị trí hoặc thứ tự khai báo của local/anonymous class. Cũng không nên đổi tên tệp `.class` bằng tay để “đổi tên kiểu” trong bytecode.

## 6. Lỗi phổ biến và cách xử lý

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Truyền `Outer.Inner` cho `Class.forName(...)` khi `Inner` là member class | Đó là cách viết nguồn/canonical name, không phải binary name | Dùng `Outer$Inner`, kèm package nếu có |
| Đọc `Outer$2Local` thành “lớp Local thứ hai trong phương thức” | Số sinh ra không là hợp đồng ổn định về thứ tự/phương thức | Dùng `getEnclosingMethod()`, `getEnclosingClass()` và metadata |
| Xem mọi lớp có `$` là anonymous class | Member, local và cả Java identifier chứa `$` có thể xuất hiện | Dùng `isAnonymousClass()` |
| Tưởng `getCanonicalName() == null` kéo theo `getName() == null` | Local/anonymous không có canonical name nhưng vẫn có tên nhị phân sau biên dịch | Phân biệt ý nghĩa từng API |
| Cho rằng lớp lồng `static` không phải member class | `static` không xóa quan hệ khai báo trực tiếp | Kiểm tra `isMemberClass()` và `getDeclaringClass()` |
| Lưu cứng tên `Outer$1` vào cấu hình dùng lâu dài | Tên compiler sinh có thể đổi sau sửa mã hoặc đổi compiler | Sử dụng API/kiểu ổn định, hoặc nhận tên từ `Class` tại runtime |

## 7. Tự kiểm tra

1. Nếu `class Outer { static class Node {} }` nằm trong package `demo`, binary name của `Node` là gì? **`demo.Outer$Node`**; canonical name là `demo.Outer.Node`.
2. Nếu `class Local {}` nằm trong phương thức và `Local.class.getCanonicalName()` trả `null`, có phải lỗi không? **Không.** Đây là hành vi đúng; `getSimpleName()` vẫn trả `Local`.
3. Nếu biên dịch hai lần cho ra chỉ số khác nhau trong anonymous class, có nên dùng chỉ số đó làm ID bền vững? **Không.** Chỉ số do compiler sinh không dành cho việc định danh trong logic ứng dụng.
4. Muốn biết một local class xuất hiện trong phương thức nào, nên bóc số sau `$` hay gọi API? **Gọi `getEnclosingMethod()`**; xét thêm `getEnclosingConstructor()` nếu có thể khai báo trong constructor.

**Ghi nhớ:** Member class có dạng binary name `Outer$Member`; local class có dạng `Outer$<digits>Local`; anonymous class có dạng `Outer$<digits>`. Dùng `getName()` khi cần tên thực tế và dùng API Reflection chuyên dụng để xác định loại lớp cùng quan hệ chứa.

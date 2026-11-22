# Cú pháp lặp và cú pháp chứa tường minh của repeatable annotation trong Java

Java cho phép gắn **nhiều annotation cùng kiểu tại một vị trí** khi annotation type đó được khai báo **@Repeatable** (từ Java 8). Có hai hình thức viết phổ biến:

**Cú pháp lặp (repeated syntax):**

~~~java
@Tag("alpha")
@Tag("beta")
class Repeated {}
~~~

**Cú pháp chứa tường minh (explicit container syntax):**

~~~java
@Tags({
    @Tag("alpha"),
    @Tag("beta")
})
class ExplicitContainer {}
~~~

Hai cách trên có thể biểu diễn cùng một tập giá trị và cho kết quả giống nhau qua **getAnnotationsByType(Tag.class)**. Nhưng để hiểu đúng cơ chế, phải phân biệt **annotation cơ sở (base annotation)**, **annotation chứa (container annotation)**, cách javac tạo container **ngầm định** và API reflection đọc **một annotation trực tiếp** so với **toàn bộ annotation lặp**.

Bài thực hành dùng Java 17+, giải thích quy tắc khai báo container, so sánh cú pháp, kiểm tra bytecode, những kết hợp bị javac từ chối và đưa ví dụ chạy độc lập với stdout đã kiểm chứng.

## 1. Khi nào được gắn nhiều annotation cùng kiểu?

Mặc định, lặp cùng annotation type tại cùng vị trí sẽ gây lỗi biên dịch:

~~~java
@interface Label {
    String value();
}

// Sai nếu Label chưa được khai báo @Repeatable:
// @Label("a")
// @Label("b")
// class Item {}
~~~

Java không tự suy ra ý nghĩa “hai nhãn” từ hai lần viết **@Label**. Muốn cú pháp này hợp lệ, kiểu Label phải chỉ ra một **containing annotation type** có thể chứa các giá trị Label.

Khai báo đủ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Repeatable(Tags.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}
~~~

Các thành phần:

- **Tag** là kiểu annotation **được phép lặp**. **@Repeatable(Tags.class)** gắn trên Tag cho biết **Tags** là kiểu container.
- **Tags** là một kiểu annotation khác, có element bắt buộc **Tag[] value()**. Element đó chứa một mảng các giá trị Tag.
- Cả hai có **@Retention(RUNTIME)** để có thể đọc bằng reflection lúc chạy. Nếu chỉ xử lý khi biên dịch, có thể dùng retention khác phù hợp.
- **@Target(TYPE)** cho phép áp dụng chúng trên khai báo class/interface/enum/annotation type. Cần phối hợp target của Tag và Tags cho vị trí dự định lặp.
- **Tag.value()** là String nên **@Tag("alpha")** tương đương **@Tag(value = "alpha")**.
- **Tags.value()** là **Tag[]**, một kiểu element mảng hợp lệ của Java.

**@Repeatable là meta-annotation của Tag, không phải một thứ được gắn lên class sử dụng.** Nó mô tả cách trình biên dịch và các API nhận biết một annotation type có thể xuất hiện nhiều lần.

## 2. Cú pháp lặp: mỗi annotation cơ sở được viết riêng

Khi viết:

~~~java
@Tag("alpha")
@Tag("beta")
class Repeated {}
~~~

hai lần sử dụng **Tag** xuất hiện liên tiếp trên cùng khai báo class. Tên **Repeated** ở đây chỉ là tên class minh họa, không liên quan đến từ khóa của Java.

Theo JLS §9.7.5, khi có từ hai annotation cùng repeatable type tại một vị trí và điều kiện target hợp lệ, javac xử lý **như thể tại vị trí đó có một annotation container ngầm định**, với các Tag ban đầu nằm trong phần tử **value()** của container.

Có thể hình dung:

~~~text
Trong source:
    @Tag("alpha")
    @Tag("beta")
    class Repeated {}

Cách hiểu của compiler:
    @Tags({
        @Tag("alpha"),
        @Tag("beta")
    })
    class Repeated {}
~~~

Sơ đồ mô tả **ngữ nghĩa**, không phải nói javac phải sửa lại file source. Người viết vẫn giữ cú pháp ngắn và dễ đọc; compiler chịu trách nhiệm thể hiện các annotation này theo quy tắc container.

### Thứ tự giá trị có được giữ lại không?

**Có.** Các annotation cơ sở được đặt trong **mảng value() của container ngầm định theo thứ tự từ trái sang phải** khi chúng xuất hiện ở vị trí annotation. Ví dụ:

~~~java
@Tag("first")
@Tag("second")
@Tag("third")
class Ordered {}
~~~

Mảng Tag trong container tương ứng có thứ tự **first, second, third**. Với reflection dùng API ByType, thứ tự các annotation tìm được phản ánh quy tắc container đó. Điều này khác với việc giả định **mọi danh sách annotations trên mọi Class đều được sắp xếp cố định**: thứ tự cần đọc theo hợp đồng API thích hợp.

**Không bắt buộc viết các Tag liên tiếp**, mặc dù cách viết liên tiếp là quy ước dễ đọc. Trọng tâm là chúng cùng xuất hiện trong **một declaration context hoặc type context** mà Java cho phép lặp.

## 3. Cú pháp chứa tường minh: tạo container bằng tay

Cùng dữ liệu có thể viết:

~~~java
@Tags({
    @Tag("alpha"),
    @Tag("beta")
})
class ExplicitContainer {}
~~~

Ở đây, người viết mã **khai báo trực tiếp Tags**, chứ không viết hai Tag độc lập ở vị trí class. Các annotation Tag nằm **bên trong giá trị của element Tags.value()**.

Có thể viết theo cú pháp đủ tên phần tử:

~~~java
@Tags(value = {
    @Tag(value = "alpha"),
    @Tag(value = "beta")
})
class ExplicitContainer {}
~~~

Hai đoạn trên tương đương về element-value. Vì tên phần tử là **value()**, Java cho phép lược bỏ **value =** ở cả container và từng Tag.

### Container với một hoặc không phần tử

Một container tường minh không nhất thiết chứa từ hai Tag trở lên:

~~~java
@Tags({@Tag("single")})
class OneInsideContainer {}

@Tags({})
class EmptyContainer {}
~~~

**OneInsideContainer** có một **Tags** trực tiếp chứa một Tag. **EmptyContainer** có Tags trực tiếp, nhưng **value()** là mảng rỗng. Khi gọi **getAnnotationsByType(Tag.class)** trên EmptyContainer, kết quả là **mảng Tag[] rỗng**, mặc dù một annotation **Tags** vẫn hiện diện.

Điều này khác với:

~~~java
@Tag("single")
class OneDirectTag {}

class NoTag {}
~~~

- **OneDirectTag** có một Tag trực tiếp; không cần compiler tổng hợp Tags, vì không có nhiều Tag cần gom.
- **NoTag** không có Tag cũng không có Tags.
- **EmptyContainer** có Tags nhưng không có Tag bên trong.
- Cả EmptyContainer và NoTag đều cho **getAnnotationsByType(Tag.class).length == 0**, nhưng **getDeclaredAnnotation(Tags.class)** phân biệt chúng.

Do đó, *“không có Tag được tìm bởi API ByType”* không luôn giống *“không có container được khai báo”*.

## 4. So sánh hai cú pháp theo source và metadata

| Đặc điểm | Cú pháp lặp | Container tường minh |
| --- | --- | --- |
| Cách viết | **@Tag("a") @Tag("b")** | **@Tags({@Tag("a"), @Tag("b")})** |
| Người viết trực tiếp đặt annotation nào lên class? | Hai **Tag** trong source | Một **Tags** trong source |
| Container tại ngữ nghĩa biên dịch | Compiler tạo ngầm khi cần | Người viết khai báo trực tiếp |
| Bảo toàn thứ tự | Theo thứ tự các Tag được viết | Theo thứ tự phần tử mảng Tags.value() |
| Lấy toàn bộ Tag khi có RUNTIME retention | **getAnnotationsByType(Tag.class)** | **getAnnotationsByType(Tag.class)** |
| Lấy Tags trực tiếp bằng reflection | Có thể tìm container do compiler sinh | Tìm container người viết khai báo |
| Đổi cách viết khi dữ liệu bằng nhau | Có thể cho kết quả ByType tương đương | Có thể cho kết quả ByType tương đương |
| Có viết container rỗng không? | Không thể có “zero lần @Tag” mà tự tạo container | Có: **@Tags({})** |
| Tập trung vào điều gì? | Dễ đọc từng nhãn, cú pháp ngắn | Nhìn rõ cấu trúc mảng chứa, thuận tiện với một số mã cũ |

**Không được kết luận hai cách luôn giống nhau về mọi phương diện.** Trình biên dịch chỉ tạo container khi có nhiều Tag lặp tại cùng vị trí; nếu chỉ có một Tag, metadata trực tiếp khác metadata của **@Tags({@Tag(...)})**. Ngoài ra, container có thể khai báo các element bổ sung có default, hoặc được xử lý riêng bởi công cụ, khiến việc chọn cú pháp có ý nghĩa ngoài các giá trị Tag mà **ByType** trả về.

### Một điểm hay bị nhầm

Cú pháp:

~~~java
@Tag("a")
@Tag("b")
class Repeated {}
~~~

**không có nghĩa** hai Tag chắc chắn được ghi thành hai annotation Tag trực tiếp riêng biệt trong **RuntimeVisibleAnnotations** của class file. Khi được lặp, javac biểu diễn chúng thông qua **container Tags**. Vì thế API cũ chỉ gọi **getAnnotation(Tag.class)** có thể trả null dù **getAnnotationsByType(Tag.class)** trả ra hai Tag.

## 5. Ví dụ Java 17+ độc lập: so sánh kết quả reflection

Tạo một file duy nhất **src/demo/RepeatSyntaxDemo.java**:

~~~java
package demo;

import java.lang.annotation.*;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("alpha")
@Tag("beta")
class Repeated {}

@Tags({@Tag("alpha"), @Tag("beta")})
class ExplicitContainer {}

@Tag("solo")
class Single {}

@Tags({})
class EmptyContainer {}

class NoTag {}

public class RepeatSyntaxDemo {
    public static void main(String[] args) {
        print(Repeated.class);
        print(ExplicitContainer.class);
        print(Single.class);
        print(EmptyContainer.class);
        print(NoTag.class);
    }

    private static void print(Class<?> type) {
        Tag[] all = type.getDeclaredAnnotationsByType(Tag.class);
        Tag direct = type.getDeclaredAnnotation(Tag.class);
        Tags container = type.getDeclaredAnnotation(Tags.class);

        String values = Arrays.toString(
                Arrays.stream(all)
                      .map(Tag::value)
                      .toArray(String[]::new));

        System.out.println(type.getSimpleName()
                + ": values=" + values
                + ", direct=" + (direct != null)
                + ", container=" + (container != null));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa **src**:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/RepeatSyntaxDemo.java
java -cp out demo.RepeatSyntaxDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
Repeated: values=[alpha, beta], direct=false, container=true
ExplicitContainer: values=[alpha, beta], direct=false, container=true
Single: values=[solo], direct=true, container=false
EmptyContainer: values=[], direct=false, container=true
NoTag: values=[], direct=false, container=false
~~~

Ví dụ được **biên dịch/chạy thực tế bằng javac JDK 21 với --release 17**. Nó sử dụng cú pháp và API có trong Java 17, nhưng nếu triển khai trên một toolchain cụ thể thì vẫn nên chạy kiểm thử trên chính JDK đó.

### Giải thích từng dòng

**Repeated:** trong source có hai **@Tag**. Vì được lặp, javac sinh container **Tags** theo quy tắc JLS. Reflection theo **getDeclaredAnnotationsByType(Tag.class)** mở container và trả Tag[] gồm alpha/beta. **getDeclaredAnnotation(Tag.class)** không xem hai Tag bên trong container là Tag trực tiếp, nên trả null. **getDeclaredAnnotation(Tags.class)** tìm được container.

**ExplicitContainer:** trong source có **@Tags({...})** trực tiếp. Trong class file cũng có Tags chứa hai Tag. Kết quả của ba phép truy vấn trên giống Repeated.

**Single:** chỉ có một **@Tag("solo")**. Nó được giữ như một Tag trực tiếp; không cần tự sinh container. Vì vậy **direct=true**, **container=false** và **getDeclaredAnnotationsByType** vẫn trả ra một phần tử.

**EmptyContainer:** container Tags có mặt nhưng mảng value rỗng, nên **values=[]**, **container=true**.

**NoTag:** không có cả base annotation lẫn container; **values=[]**, **direct=false**, **container=false**.

**Vì sao dùng getDeclaredAnnotationsByType?** Ví dụ chỉ so sánh annotation được khai báo/được chứa trên chính từng class, không có superclass hay @Inherited. API **Declared...ByType** cho phép lấy Tag[] trực tiếp hoặc gián tiếp trong container, không bị làm nhiễu bởi annotation ở class cha.

## 6. Kiểm tra class file bằng javap

Sau khi biên dịch, dùng:

~~~bash
javap -v -p out/demo/Repeated.class
javap -v -p out/demo/ExplicitContainer.class
javap -v -p out/demo/Single.class
~~~

Quan sát phần **RuntimeVisibleAnnotations**:

- **Repeated.class** có metadata **demo.Tags** với phần tử **value** chứa hai **demo.Tag**.
- **ExplicitContainer.class** cũng có **demo.Tags** chứa hai Tag.
- **Single.class** có annotation **demo.Tag** trực tiếp; không cần container Tags.

Không nên so sánh bytecode từng ký tự hoặc chỉ số constant pool, vì chúng có thể khác giữa phiên bản compiler. Mục tiêu là xác nhận **Tag lặp được biểu diễn bằng container annotation**, không phải hai entry Tag trực tiếp độc lập.

Một phần thông tin minh họa từ **javap -v** sau khi biên dịch Repeated:

~~~text
RuntimeVisibleAnnotations:
  ...
    demo.Tags(
      value=[@demo.Tag(
        value="alpha"
      ),@demo.Tag(
        value="beta"
      )]
    )
~~~

Dấu **...** ở đây biểu thị chỉ số constant-pool/chi tiết khác được lược bỏ trong đoạn trích, **không phải đầu ra nguyên văn hoàn chỉnh của javap**. Phần tên annotation và giá trị là nội dung quan trọng.

### Ngầm định nghĩa là gì?

**Container ngầm định** chỉ nói người viết không gõ trực tiếp **@Tags** tại vị trí class. Compiler vẫn tạo metadata có ngữ nghĩa container. **Không tồn tại một cơ chế runtime tự đi gom nhiều Tag bằng cách quét chữ @ trong source**; lúc chương trình chạy, reflection làm việc với metadata class file đã được compiler tạo.

## 7. getAnnotation khác getAnnotationsByType như thế nào?

Đây là sự khác biệt quan trọng nhất khi tiêu thụ repeatable annotation.

**getAnnotation(Tag.class)** hỏi một annotation Tag **present** trên phần tử theo hợp đồng **AnnotatedElement**. Nó **không tự mở container Tags** để trả từng Tag bị chứa gián tiếp.

**getAnnotationsByType(Tag.class)** là API có hỗ trợ repeatable annotation, có thể **mở container** để trả mọi Tag tương ứng. Đối với Class và annotation type có @Inherited, API này còn tuân theo quy tắc annotation **associated** theo Javadoc.

**getDeclaredAnnotation(Tag.class)** chỉ xét Tag được khai báo trực tiếp, không tính kết quả inherited.

**getDeclaredAnnotationsByType(Tag.class)** xét Tag trực tiếp **và Tag chứa gián tiếp** trong container tại chính phần tử, bỏ qua superclass.

**getAnnotation(Tags.class)** hoặc **getDeclaredAnnotation(Tags.class)** hỏi về **container Tags** như một annotation type riêng. Nó không trả mảng Tag trực tiếp; phải gọi **container.value()** mới có mảng.

Bảng khi mọi annotation đều có RUNTIME retention và không có @Inherited:

| Trường hợp | getAnnotation(Tag.class) | getAnnotationsByType(Tag.class) | getAnnotation(Tags.class) |
| --- | --- | --- | --- |
| Hai Tag lặp | **null** | **[alpha, beta]** | Tags chứa hai Tag |
| Container Tags tường minh chứa hai Tag | **null** | **[alpha, beta]** | Tags chứa hai Tag |
| Một Tag trực tiếp | Tag("solo") | **[solo]** | null |
| Tags container rỗng | null | **[]** | Tags chứa mảng rỗng |
| Không gắn Tag/Tags | null | **[]** | null |

Một câu lệnh đúng để lấy tất cả Tag:

~~~java
Tag[] tags = SomeType.class.getAnnotationsByType(Tag.class);
for (Tag tag : tags) {
    System.out.println(tag.value());
}
~~~

Đây là mã minh họa, **SomeType** cần là một class đã tồn tại. Khi dùng repeatable annotation, không nên viết bộ quét chỉ dùng **getAnnotation(Tag.class)** rồi kết luận null có nghĩa không có Tag nào.

### isAnnotationPresent(Tag.class) cũng có giới hạn tương tự

Theo hợp đồng **AnnotatedElement**, **isAnnotationPresent(Tag.class)** có cùng kết quả boolean với **getAnnotation(Tag.class) != null**. Vì vậy nó cũng có thể **false khi có hai Tag nằm trong container**.

~~~java
boolean onePresent =
        Repeated.class.isAnnotationPresent(Tag.class);
Tag[] all =
        Repeated.class.getAnnotationsByType(Tag.class);

// onePresent == false
// all.length == 2
~~~

**Không dùng isAnnotationPresent(Tag.class) để quyết định liệu một class có ít nhất một repeatable Tag dưới mọi dạng hay không.** Nếu cần câu hỏi đó, dùng **getAnnotationsByType(Tag.class).length > 0**.

## 8. Quy tắc không thể trộn nhiều Tag với container tại cùng vị trí

Java không cho phép tự do kết hợp mọi dạng lặp và dạng container. Theo JLS §9.7.5:

**Không hợp lệ:** tại cùng declaration/type context có **nhiều annotation cơ sở @Tag** cùng với **bất kỳ annotation container @Tags**:

~~~java
// Lỗi biên dịch: có hai Tag và một container trên cùng class.
// @Tag("a")
// @Tag("b")
// @Tags({@Tag("c")})
// class InvalidMix {}
~~~

Lý do: hai Tag cơ sở đã buộc compiler tạo một container ngầm. Nếu lại có container tường minh, kết quả sẽ có nhiều lớp chứa chồng lên nhau hoặc quy tắc hợp nhất mơ hồ.

**Có thể hợp lệ:** một base annotation **@Tag** xuất hiện cùng **một container @Tags**:

~~~java
@Tag("direct")
@Tags({@Tag("nested")})
class MixedButLegal {}
~~~

Đây là cú pháp **được JLS cho phép** và đã được javac --release 17 kiểm tra. Vì chỉ có một Tag cơ sở nên nó không cần tạo container ngầm định từ nhiều Tag. Tuy vậy, việc một vị trí vừa có Tag trực tiếp vừa có Tags container làm mô hình metadata khó giải thích hơn; với API công khai, nên ưu tiên một cách biểu diễn nhất quán.

**Không hợp lệ:** một Tag cơ sở đi cùng **nhiều container @Tags** trên cùng vị trí, ví dụ:

~~~java
// Lỗi biên dịch theo JLS:
// @Tag("direct")
// @Tags({@Tag("first")})
// @Tags({@Tag("second")})
// class InvalidContainers {}
~~~

Một container Tags thông thường không tự được lặp, trừ khi chính nó được thiết kế repeatable theo một cấp chứa khác; ngay cả khi có cấp khác, JLS vẫn hạn chế những trường hợp trộn mơ hồ.

**Khuyến nghị:** trong mã bình thường, chọn **nhiều @Tag** hoặc **một @Tags({...})**, đừng kết hợp khi không có yêu cầu đặc biệt. Điều này giảm khác biệt giữa API đọc Tag trực tiếp và API mở container.

## 9. Các điều kiện bắt buộc đối với container annotation type

Không phải bất kỳ annotation nào có mảng Tag cũng trở thành một containing annotation type hợp lệ. JLS §9.6.3 đặt ra các ràng buộc.

### 9.1. Element value() phải trả đúng mảng base annotation

~~~java
@interface Tags {
    Tag[] value();
}
~~~

Đúng: **Tag[]** là kiểu trả về của **value()**.

Sai:

~~~java
// Không phải containing type hợp lệ của Tag:
// @interface Tags {
//     Object[] value();
// }
~~~

**Object[]** là kiểu annotation element không hợp lệ và không đáp ứng yêu cầu Tag[]. **String[]** cũng không thể thay cho **Tag[]** nếu container được khai báo cho Tag.

### 9.2. Mọi element phụ trong container phải có default

Container có thể khai báo thêm element:

~~~java
@interface Tags {
    Tag[] value();
    String source() default "local";
}
~~~

**source()** có default nên khi compiler tạo container ngầm định, nó không buộc tác giả của từng @Tag phải cung cấp source.

Không hợp lệ khi làm container của Tag:

~~~java
// @interface Tags {
//     Tag[] value();
//     String source(); // thiếu default
// }
~~~

Nếu có element phụ bắt buộc, javac không biết lấy giá trị gì khi tự sinh container từ các @Tag lặp, do đó từ chối định nghĩa repeatable type dùng container này.

**Một hệ quả thiết kế:** hai cách viết lặp và chứa tường minh có thể có khác biệt bổ sung nếu container có element phụ. Với repeated syntax, container ngầm định dùng default của element phụ; với explicit container, người viết có thể cung cấp giá trị khác default. Vì thế, khi xây công cụ, cần xác định mình chỉ quan tâm các base annotations hay cả metadata ở container.

### 9.3. Retention của container không được ngắn hơn retention của base

Ví dụ phù hợp để đọc runtime:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Tags {
    Tag[] value();
}
~~~

Đây chỉ minh họa **retention** và thiếu @Repeatable/@Target cần thiết cho đoạn chương trình đầy đủ. Điều kiện là **containing type phải có retention ít nhất dài bằng base annotation type** theo SOURCE, CLASS, RUNTIME.

Nếu Tag có **RUNTIME** nhưng Tags chỉ có **CLASS**, container có thể biến mất khỏi reflection runtime ngay khi Tag được lặp — đó là cấu hình không được JLS cho phép.

**Retention mặc định là CLASS** nếu không chỉ định @Retention. Vì vậy, với repeatable annotation cần đọc bằng reflection, nên khai báo **@Retention(RUNTIME)** nhất quán cho base và container.

### 9.4. Target của base và container phải tương thích

Container không thể tùy tiện áp dụng trên những vị trí mà base annotation không cho phép. JLS yêu cầu vị trí phù hợp theo các quy tắc tương thích của @Target, bao gồm các trường hợp đặc biệt của **ANNOTATION_TYPE**, **TYPE**, **TYPE_PARAMETER** và **TYPE_USE**.

Thực tiễn đơn giản nhất: nếu muốn lặp Tag trên **TYPE**, cho **Tag** và **Tags** đều có **@Target(TYPE)**.

~~~java
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag { String value(); }

@Target(ElementType.TYPE)
@interface Tags { Tag[] value(); }
~~~

Đoạn này chỉ mô tả cấu hình target, bỏ qua import và retention cho ngắn. Nếu muốn dùng trên METHOD, FIELD, PARAMETER hay TYPE_USE, hãy kiểm tra target của cả hai và viết test javac tương ứng. Annotation type có @Target phù hợp cho một lần dùng **không nhất thiết được phép lặp tại mọi vị trí**, vì để lặp cần cả container có thể xuất hiện ở ngữ cảnh đó.

### 9.5. @Documented và @Inherited cần được phối hợp

Nếu base annotation type có **@Documented**, container phải có **@Documented**. Nếu base có **@Inherited**, container phải có **@Inherited**. JLS cho phép container có các meta-annotation này ngay cả khi base không có, nhưng không cho base yêu cầu chúng mà container bỏ thiếu.

Những quy tắc này tồn tại để metadata lặp không mất đi ý nghĩa khi compiler biểu diễn base bằng container.

## 10. Repeatable annotation và @Inherited

**@Inherited** cho phép class con được truy vấn metadata từ superclass theo điều kiện Java quy định. Khi kết hợp repeatable annotation với @Inherited, cần hiểu sự khác biệt giữa **present** và **associated**.

Ví dụ các khai báo (rút gọn, giả định import phù hợp):

~~~java
@Inherited
@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}

@Role("reader")
@Role("auditor")
class Base {}

class Child extends Base {}
~~~

Khi gọi **Child.class.getAnnotationsByType(Role.class)**, có thể nhận hai Role từ Base thông qua quy tắc **associated annotations** của AnnotatedElement. **Child.class.getDeclaredAnnotationsByType(Role.class)** trả mảng rỗng vì Child không khai báo trực tiếp các Role.

**Không nhầm** điều đó với **Child.class.getAnnotation(Role.class)**: vì hai Role ở Base được biểu diễn qua container, một truy vấn đòi duy nhất Role *present* có thể không tìm thấy một Role trực tiếp, trong khi ByType vẫn tìm được các giá trị được chứa và kế thừa.

Nếu Child khai báo Role trực tiếp hoặc gián tiếp, các giá trị trên Child được ưu tiên theo quy tắc associated; không mặc nhiên cộng dồn danh sách của Base với Child. Một framework muốn gộp Role nhiều cấp class phải đặt quy tắc riêng.

**@Inherited không áp dụng theo đường implements interface**, và không tự truyền annotation trên method đã override. Đây là giới hạn chung của @Inherited, không thay đổi chỉ vì annotation type có @Repeatable.

## 11. Container tường minh và khả năng chuyển đổi mã cũ

Có thể gặp mã dùng container trước khi kiểu annotation được đánh dấu **@Repeatable**:

~~~java
@Tags({
    @Tag("internal"),
    @Tag("beta")
})
class OldStyle {}
~~~

Nếu Tag, Tags được khai báo hợp lệ nhưng Tag chưa có @Repeatable, cú pháp container tường minh vẫn có thể là annotation bình thường: **Tags** chỉ là một kiểu annotation sở hữu phần tử **Tag[] value()**. Người viết không cần lặp @Tag trực tiếp trên class.

Sau khi thay Tag thành repeatable với **@Repeatable(Tags.class)**, các API **getAnnotationsByType(Tag.class)** có thể bắt đầu nhận diện và mở Tags như containing annotation type. Đây là khác biệt hành vi của API reflection nếu trước đó hệ thống chỉ đọc Tag/Tags theo cơ chế riêng.

**Không đồng nhất source compatibility, binary compatibility và behavioral compatibility.** Việc nâng cấp một annotation type từ không repeatable sang repeatable có thể giữ tính tương thích về liên kết binary, nhưng thay đổi kết quả của API ByType khi container trước đó không được coi là container của repeatable annotation.

Đối với thư viện:

- Khi chỉ muốn người dùng ghi nhiều nhãn, cú pháp lặp **@Tag("x") @Tag("y")** thường tự nhiên và dễ đọc.
- Khi dùng hệ thống cũ có cấu trúc container riêng, cú pháp **@Tags({...})** có thể giúp giữ hợp đồng hiện tại.
- Khi cần đọc tất cả nhãn trong API mới, ưu tiên **getAnnotationsByType(Tag.class)** và kiểm tra cả trường hợp Tag trực tiếp, container implicit, container explicit.
- Khi muốn phân biệt mã nguồn đã dùng dạng nào, **reflection runtime thông thường không tái dựng được nguyên văn cú pháp gốc**. Cần phân tích source bằng công cụ thích hợp; hai dạng với cùng metadata sau biên dịch có thể không phân biệt được qua reflection.

## 12. Annotation lặp trên METHOD, FIELD và TYPE_USE

Bản ví dụ runnable ở trên gắn Tag lên class để tập trung vào cú pháp container. Nhưng @Repeatable không chỉ dành cho class; nó có thể dùng ở nhiều nơi nếu target cho phép.

**Trên phương thức:**

~~~java
@Target(ElementType.METHOD)
@Repeatable(Checks.class)
@interface Check {
    String value();
}

@Target(ElementType.METHOD)
@interface Checks {
    Check[] value();
}

class Service {
    @Check("authenticated")
    @Check("logged")
    void process() {}
}
~~~

Nếu định đọc qua reflection runtime, phải bổ sung **@Retention(RUNTIME)** cho cả Check và Checks. Khi đó lấy Method từ Class rồi gọi **method.getAnnotationsByType(Check.class)** để nhận các rule.

**Trên type use:**

~~~java
@Target(ElementType.TYPE_USE)
@Repeatable(Qualifiers.class)
@interface Qualifier {
    String value();
}

@Target(ElementType.TYPE_USE)
@interface Qualifiers {
    Qualifier[] value();
}

class Repository {
    java.util.List<@Qualifier("readonly")
                   @Qualifier("trusted") String> names;
}
~~~

Đoạn minh họa nêu cú pháp; cần import meta-annotation, và thêm runtime retention nếu muốn reflection đọc vị trí type use. Với type annotations, đọc qua **AnnotatedType** hoặc **AnnotatedParameterizedType** của field/method thay vì gọi trực tiếp **Field.getAnnotation(Qualifier.class)**.

**Điểm chung:** việc lặp chỉ được phép ở vị trí mà **base và container cùng có khả năng áp dụng** theo JLS. Cú pháp lặp không bỏ qua quy tắc target.

## 13. Lỗi phổ biến và cách khắc phục

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Lặp @Tag hai lần mà javac báo không repeatable | Thiếu **@Repeatable(Tags.class)** | Đăng ký container đúng trên Tag |
| @Repeatable trỏ tới container có **String[] value()** | Container phải có **Tag[] value()** | Sửa kiểu phần tử value |
| Container có element phụ không có default | Compiler không thể tạo container ngầm | Thêm default hợp lệ hoặc loại bỏ phần tử |
| Tag giữ RUNTIME nhưng Tags chỉ giữ CLASS | Retention của container ngắn hơn base | Dùng RUNTIME cho Tags |
| @Tag dùng được nhưng lặp ở vị trí nào đó bị từ chối | Target của container không phù hợp vị trí | Kiểm tra @Target của cả hai |
| Lặp @Tag và đồng thời viết @Tags trên cùng vị trí | Nhiều Tag + container gây lỗi JLS | Chọn repeated syntax hoặc một explicit container |
| Chỉ dùng getAnnotation(Tag.class) rồi kết luận không có nhãn | API không mở container | Dùng getAnnotationsByType(Tag.class) |
| isAnnotationPresent(Tag.class) cho false dù nhìn thấy hai @Tag | Tương đương getAnnotation(Tag.class) != null | Dùng **ByType.length > 0** |
| Mong một Tag tự sinh một container | Compiler không cần container nếu chỉ một Tag | Kiểm tra cả dạng trực tiếp |
| Mong container rỗng giống hoàn toàn không có annotation | Tags vẫn có mặt trong metadata | Truy vấn Tags riêng nếu trạng thái đó có ý nghĩa |
| Coi @Tags({...}) có nghĩa Tags cũng là repeatable | Container không tự repeatable chỉ vì chứa Tag[] | Chỉ base type có @Repeatable mới được lặp |
| Thiếu @Retention(RUNTIME) nhưng gọi reflection | Mặc định retention là CLASS | Gắn RUNTIME đúng trên base/container |
| Dùng Class.getAnnotation cho type-use annotation | Truy vấn sai vị trí metadata | Dùng API AnnotatedType thích hợp |
| Đoán thứ tự bằng getDeclaredAnnotations() không liên quan | Không phải API mô tả mọi quy tắc thứ tự Tag | Dùng getAnnotationsByType và quy tắc của container |

## 14. Bài tập tự kiểm tra

**Bài 1.** Với hai khai báo:

~~~java
@Tag("red")
@Tag("blue")
class A {}

@Tags({@Tag("red"), @Tag("blue")})
class B {}
~~~

**Câu hỏi:** A và B có kết quả **getDeclaredAnnotationsByType(Tag.class)** giống nhau không? **Có:** cả hai trả mảng hai Tag với giá trị red/blue theo thứ tự trong source/container.

**Bài 2.** Với A và B, **getDeclaredAnnotation(Tag.class)** có trả một Tag không? **Không** trong hai trường hợp hai giá trị đã được chứa qua Tags; gọi API này cho null.

**Bài 3.** Với **@Tag("only") class C {}**, reflection có bắt buộc tìm **Tags** không? **Không.** Một Tag trực tiếp không cần container ngầm. **getAnnotationsByType(Tag.class)** vẫn trả mảng một phần tử.

**Bài 4.** Với **@Tags({}) class D {}**, **D.class.getAnnotationsByType(Tag.class).length** là bao nhiêu? **0**. Nhưng **D.class.getAnnotation(Tags.class)** vẫn có thể khác null nếu Tags được giữ ở runtime.

**Bài 5.** Nếu container chứa **Tag[] value(); String source();** nhưng source không có default, nó có thể là containing annotation type của Tag không? **Không.** Mọi element khác value() trên container cần có default.

**Bài 6.** Nếu Tag chỉ có **@Target(METHOD)** còn Tags chỉ có **@Target(FIELD)**, có thể lặp Tag trên method không? **Không**, vì container không áp dụng được lên method và quan hệ target không hợp lệ đối với containing type.

**Bài 7.** Có được viết **@Tag("one") @Tags({@Tag("two")})** trên cùng class không? **Có thể được JLS cho phép** khi đúng một Tag cơ sở và đúng một container, nhưng API khó đọc hơn. Không được viết thêm một Tag thứ hai bên cạnh container.

**Bài 8.** Muốn đọc các annotation lặp trên **List<@Qualifier("a") @Qualifier("b") String>** ở runtime, có thể lấy **Field.getAnnotation(Qualifier.class)** không? **Không** nếu Qualifier chỉ là TYPE_USE. Phải lấy **AnnotatedType** thích hợp và gọi **getAnnotationsByType(Qualifier.class)** trên đúng vị trí kiểu.

**Bài 9.** Thay cú pháp lặp bằng container tường minh có luôn khôi phục được từ class file không? **Không.** Với các giá trị tương đương, compiler có thể ghi cùng dạng container metadata; reflection không phải công cụ giữ nguyên cú pháp nguồn ban đầu.

## 15. Nguồn tham khảo chính thức

- **Java Language Specification §9.6.3 — Repeatable Annotation Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3 — quy tắc container value(), retention, target, Documented và Inherited.
- **Java Language Specification §9.7.5 — Multiple Annotations of the Same Interface:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.5 — cú pháp lặp, container ngầm định, thứ tự và giới hạn kết hợp container.
- **Java SE 17 — java.lang.annotation.Repeatable:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html — meta-annotation cho base annotation type.
- **Java SE 17 — java.lang.reflect.AnnotatedElement:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html — trực tiếp/gián tiếp, present/associated, getAnnotation và getAnnotationsByType.
- **Java SE 17 — java.lang.annotation.RetentionPolicy:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html — SOURCE, CLASS, RUNTIME.

**Ghi nhớ:** **@Tag("a") @Tag("b")** là cú pháp lặp khiến compiler tạo **container Tags ngầm định**; **@Tags({@Tag("a"), @Tag("b")})** là cú pháp **khai báo container tường minh**. Hai dạng thường cho cùng danh sách khi đọc bằng **getAnnotationsByType(Tag.class)**, nhưng API **getAnnotation(Tag.class)** có thể không thấy Tag chứa trong container. Thiết kế base/container cho đúng quy tắc JLS và dùng đúng API là chìa khóa để khai thác repeatable annotation an toàn.

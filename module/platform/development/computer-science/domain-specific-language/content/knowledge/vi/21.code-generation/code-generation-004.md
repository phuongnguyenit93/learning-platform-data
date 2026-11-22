# Quản lý import

Trong giai đoạn **sinh mã** (*code generation*) của một DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), compiler thường chuyển các symbol đã được phân giải trong chương trình DSL thành tên kiểu, hàm, module hoặc API của ngôn ngữ đích. Nếu mã đích nằm trong nhiều package hoặc module, compiler còn phải tạo và quản lý các khai báo `import` tương ứng.

**Quản lý import** là quá trình xác định những symbol mà mã được sinh ra cần sử dụng, quyết định cách tham chiếu chúng trong ngôn ngữ đích, phát hiện xung đột tên, tạo danh sách import hợp lệ và ghi chúng vào vị trí thích hợp trong tệp đầu ra.

Ví dụ, DSL có thể khai báo:

```text
service Catalog {
    items: List<Product>
    createdAt: Instant
}
```

Nếu backend sinh Java, mã đầu ra có thể cần:

```java
import java.time.Instant;
import java.util.List;

public class Catalog {
    private List<Product> items;
    private Instant createdAt;
}
```

Danh sách import không nên được tạo bằng cách quét chuỗi đầu ra sau khi sinh mã. Cách đáng tin cậy hơn là để quá trình sinh mã ghi nhận các symbol đích mà nó thực sự tham chiếu, sau đó một import manager quyết định cách viết và xuất các import.

Quản lý import ảnh hưởng trực tiếp đến tính đúng đắn và khả năng biên dịch của mã sinh ra. Một import thiếu có thể khiến mã không biên dịch; một import sai có thể trỏ đến kiểu khác cùng tên; một import thừa có thể làm mã khó đọc hoặc vi phạm quy tắc lint; thứ tự không ổn định có thể tạo thay đổi không cần thiết giữa các lần sinh mã.

## 1. Import trong mã nguồn đích

Import là khai báo cho phép mã nguồn tham chiếu đến thành phần được định nghĩa ở package, module hoặc namespace khác bằng một tên ngắn hơn hoặc theo quy tắc tra cứu của ngôn ngữ đích.

Ví dụ Java:

```java
import java.time.Instant;
import java.util.List;
```

Sau đó mã có thể viết `Instant` và `List` thay vì dùng tên đầy đủ `java.time.Instant` và `java.util.List` ở mọi vị trí.

Một ngôn ngữ khác có cú pháp khác. Kotlin dùng `import`, TypeScript dùng `import ... from`, Python dùng `import` hoặc `from ... import`, còn một số ngôn ngữ dùng module declaration hoặc namespace directive. Vì vậy, import manager cần biết quy tắc của **target language** thay vì giả định mọi backend dùng cùng một mô hình.

### 1.1. Import và tên đầy đủ

Tên đầy đủ (*fully qualified name*) xác định symbol qua toàn bộ đường dẫn namespace hoặc module. Ví dụ:

```text
java.time.Instant
```

Import cho phép dùng tên ngắn:

```java
import java.time.Instant;

Instant createdAt;
```

Nếu không import, một số ngôn ngữ vẫn cho phép dùng tên đầy đủ trực tiếp:

```java
java.time.Instant createdAt;
```

Do đó, import là một cách tổ chức tham chiếu tên, không nhất thiết là thao tác tải thư viện hoặc liên kết thư viện tại thời điểm chạy. Việc phân giải dependency và liên kết module có thể là các cơ chế riêng.

### 1.2. Import không đồng nghĩa với dependency declaration

Một dự án có thể cần khai báo dependency trong file cấu hình build, đồng thời cần import symbol trong từng tệp mã nguồn.

Ví dụ:

```text
build configuration:
    dependency "com.example:json-library:2.0"
```

```java
import com.example.json.JsonObject;
```

Dependency declaration cho build system biết thư viện nào cần có trong classpath hoặc module path. Import cho compiler của ngôn ngữ đích biết tên `JsonObject` được tham chiếu từ đâu. Có import nhưng thiếu dependency vẫn có thể không biên dịch; có dependency nhưng không import cũng có thể không phân giải được tên ngắn.

## 2. Vì sao code generator cần import manager?

Khi compiler sinh mã từ DSL, các node AST hoặc IR có thể tham chiếu đến nhiều kiểu và API khác nhau. Nếu mỗi visitor tự viết tên đầy đủ hoặc tự thêm import, logic sẽ bị phân tán và dễ không nhất quán.

Import manager tập trung các trách nhiệm:

- Nhận yêu cầu tham chiếu symbol từ các phần của code generator.
- Xác định tên đích và đường dẫn import tương ứng.
- Phát hiện nhiều symbol có cùng tên đơn giản.
- Chọn import tên đơn giản, alias hoặc tên đầy đủ theo khả năng target language.
- Loại bỏ import trùng và import không dùng.
- Nhóm và sắp xếp import theo quy ước.
- Sinh phần header/import section đúng cú pháp.
- Giữ kết quả ổn định giữa các lần chạy.

Nhờ đó, code generator chỉ cần yêu cầu “tôi cần kiểu `Instant` của package `java.time`”, thay vì tự quyết định cách viết khai báo import trong từng backend.

## 3. Phân biệt symbol DSL và symbol của ngôn ngữ đích

Một symbol trong DSL không nhất thiết ánh xạ một-một sang symbol trong target language.

Ví dụ DSL:

```text
field createdAt: Timestamp
```

Backend Java có thể ánh xạ `Timestamp` thành `java.time.Instant`, trong khi backend TypeScript có thể ánh xạ thành `Date`.

Vì vậy, import manager nên làm việc với **target symbol** sau khi mapping, hoặc nhận một đối tượng mô tả target symbol đã được backend xác định.

Một mô hình khái niệm:

```text
TargetSymbol {
    qualifiedName: "java.time.Instant"
    simpleName: "Instant"
    packageName: "java.time"
    kind: Type
    target: Java
}
```

Đây chỉ là ví dụ cấu trúc. Backend có thể cần thêm thông tin như module, nested type, generic arguments, static member, type-only status hoặc cách escape tên.

### 3.1. Không suy ra import chỉ từ tên cuối

Hai target symbol có thể cùng tên ngắn:

```text
java.util.Date
java.sql.Date
```

Nếu chỉ lưu `Date`, import manager không thể biết symbol nào được sử dụng. Cần giữ danh tính đầy đủ hoặc một `SymbolId` liên kết đến metadata của target symbol.

### 3.2. Giữ mapping ở backend

DSL frontend có thể biểu diễn `Timestamp` như một kiểu miền. Backend Java ánh xạ sang `Instant`, backend TypeScript ánh xạ sang `Date`, còn backend Python có thể dùng `datetime.datetime`.

Import manager của từng backend nhận target symbol đã được chọn, vì quy tắc import và cú pháp module của các ngôn ngữ này khác nhau.

## 4. Quy trình quản lý import

Một quy trình phổ biến gồm các bước:

```text
DSL AST / IR
    |
    v
Target type and API mapping
    |
    v
Code generation requests target symbols
    |
    v
Import collection
    |
    v
Conflict and visibility analysis
    |
    v
Import normalization and ordering
    |
    v
Render import declarations
    |
    v
Generated source file
```

### 4.1. Thu thập yêu cầu import

Khi sinh một kiểu, annotation, superclass, hàm hoặc biểu thức, generator yêu cầu import manager tham chiếu target symbol tương ứng.

Ví dụ:

```text
writer.writeType(imports.reference(java.time.Instant))
```

Phương thức `reference` có thể trả về tên sẽ được dùng trong mã, đồng thời ghi nhận symbol để xuất import sau này.

### 4.2. Phân tích xung đột

Sau khi thu thập symbol, manager kiểm tra xem có hai symbol khác nhau cùng tên đơn giản hay không. Nếu có, nó cần chọn alias hoặc dùng tên đầy đủ.

### 4.3. Chuẩn hóa và sắp xếp

Các import tương đương được hợp nhất, sau đó sắp xếp theo quy tắc của dự án hoặc formatter. Việc này giúp đầu ra ổn định và dễ đọc.

### 4.4. Render

Cuối cùng, backend tạo các dòng import theo grammar của target language và chèn vào vị trí hợp lệ trong tệp.

## 5. Mô hình dữ liệu cho import manager

Import manager thường cần một cấu trúc lưu target symbol được yêu cầu và cách tham chiếu đã chọn.

Ví dụ mô hình khái niệm:

```text
ImportRequest {
    symbolId: SymbolId
    qualifiedName: "java.time.Instant"
    simpleName: "Instant"
    kind: Type
    usageSite: SourceLocation
}

ImportDecision {
    symbolId: SymbolId
    referenceText: "Instant"
    importDeclaration: "java.time.Instant"
    alias: None
}
```

`ImportRequest` ghi nhận nhu cầu sử dụng symbol. `ImportDecision` là kết quả sau khi manager đã kiểm tra xung đột và quy tắc target language.

### 5.1. Symbol identity

Không nên dùng riêng chuỗi tên ngắn làm khóa. Khóa có thể gồm target ID, module/package và qualified name, hoặc một symbol identity do backend cấp.

### 5.2. Loại symbol

Import manager có thể cần phân biệt:

- Type hoặc class.
- Function hoặc method.
- Constant hoặc value.
- Namespace hoặc module.
- Annotation/decorator.
- Static member.
- Type-only symbol.
- Extension function.

Một số ngôn ngữ import các loại symbol bằng cùng cú pháp, một số ngôn ngữ phân biệt rõ. Metadata loại symbol giúp backend render đúng.

### 5.3. Vị trí sử dụng

Vị trí sử dụng có ích cho diagnostic khi xảy ra xung đột. Nếu `Date` được dùng ở ba chỗ và hai package cùng định nghĩa `Date`, manager có thể báo vị trí các lần sử dụng liên quan hoặc chọn cách viết an toàn.

## 6. Tên đơn giản, tên đầy đủ và alias

Import manager thường phải chọn cách tham chiếu target symbol trong mã sinh ra.

### 6.1. Dùng tên đơn giản

Nếu không có xung đột và target language hỗ trợ import thông thường, manager có thể sinh:

```java
import java.time.Instant;

Instant createdAt;
```

Đây thường là lựa chọn ngắn gọn và dễ đọc.

### 6.2. Dùng tên đầy đủ

Nếu có xung đột, manager có thể không import một hoặc cả hai symbol và dùng qualified name tại nơi tham chiếu:

```java
java.util.Date utilDate;
java.sql.Date sqlDate;
```

Cách này tránh xung đột tên đơn giản. Trong Java, nếu dùng tên đầy đủ ở vị trí type reference thì không cần import tương ứng.

### 6.3. Dùng alias

Một số ngôn ngữ cho phép alias import. Ví dụ Kotlin:

```kotlin
import java.util.Date as UtilDate
import java.sql.Date as SqlDate

val created: UtilDate? = null
val persisted: SqlDate? = null
```

TypeScript cũng hỗ trợ alias:

```typescript
import { Date as CustomDate } from "./custom-date";
```

Không phải target language nào cũng hỗ trợ alias theo cùng cách. Backend phải biết cú pháp và quy tắc phạm vi alias của ngôn ngữ đích.

### 6.4. Quy tắc chọn cách tham chiếu

Một chiến lược phổ biến:

1. Dùng tên đơn giản nếu nó không xung đột và có thể import.
2. Nếu có xung đột, dùng alias nếu target language hỗ trợ và alias ổn định.
3. Nếu không có alias hoặc alias không phù hợp, dùng tên đầy đủ.
4. Nếu symbol không thể tham chiếu hợp lệ, phát diagnostic thay vì tạo import sai.

Chính sách cụ thể có thể ưu tiên tên đầy đủ để tránh alias khó đọc, hoặc ưu tiên alias để mã gọn. Điều quan trọng là quyết định phải nhất quán.

## 7. Phát hiện và giải quyết xung đột tên

Xung đột xảy ra khi hai target symbol khác nhau có cùng tên đơn giản trong cùng phạm vi import.

Ví dụ:

```text
java.util.Date
java.sql.Date
```

Nếu mã sinh ra cần cả hai, import manager không thể tạo đồng thời:

```java
import java.util.Date;
import java.sql.Date;
```

và sau đó dùng `Date` cho cả hai, vì tên trở nên mơ hồ.

### 7.1. Bảng theo dõi tên đơn giản

Manager có thể duy trì ánh xạ:

```text
simpleName -> set of target symbols
```

Ví dụ:

```text
Date -> { java.util.Date, java.sql.Date }
Instant -> { java.time.Instant }
List -> { java.util.List }
```

Nếu một tên chỉ có một symbol, có thể dùng tên ngắn. Nếu có nhiều symbol, manager phải áp dụng chính sách conflict.

### 7.2. Xung đột với tên khai báo trong tệp hiện tại

Không chỉ các import mới xung đột với nhau. Một kiểu được sinh trong cùng tệp cũng có thể trùng tên với target symbol:

```java
package generated;

class Date { }
```

Nếu tệp cần `java.util.Date`, import manager không thể giả định tên `Date` sẽ luôn trỏ đến kiểu thư viện. Nó cần áp dụng quy tắc name resolution của Java và có thể dùng `java.util.Date` đầy đủ.

### 7.3. Xung đột với tên trong cùng package

Một số ngôn ngữ tự động nhìn thấy các kiểu cùng package hoặc module mà không cần import. Import manager phải tính đến các symbol đó, vì import một symbol cùng tên từ package khác có thể bị cấm hoặc gây mơ hồ.

### 7.4. Xung đột alias

Nếu hai import cùng dùng alias `Json`, manager cần tạo alias khác nhau hoặc chuyển một tham chiếu sang qualified name. Alias được sinh nên ổn định và dễ hiểu, ví dụ `JsonCore` và `JsonSchema`, thay vì thêm số ngẫu nhiên.

### 7.5. Không giải quyết xung đột bằng cách chọn tùy ý

Chọn symbol đầu tiên được gặp có thể khiến kết quả phụ thuộc thứ tự duyệt AST. Cùng một chương trình có thể sinh mã khác nhau nếu thứ tự traversal thay đổi. Conflict resolution cần dựa trên tập symbol đầy đủ và một quy tắc xác định.

## 8. Import trùng và loại bỏ import không dùng

Trong lúc sinh mã, cùng một target symbol có thể được yêu cầu nhiều lần.

Ví dụ:

```text
field createdAt: Instant
field updatedAt: Instant
function now(): Instant
```

Ba lần sử dụng chỉ cần một import:

```java
import java.time.Instant;
```

Import manager nên khử trùng lặp dựa trên symbol identity hoặc import key đã chuẩn hóa.

### 8.1. Import trùng

Nếu cùng một import được yêu cầu nhiều lần, chỉ xuất một khai báo. Không nên dựa vào việc loại bỏ chuỗi giống nhau ở cuối pipeline nếu hai chuỗi có thể khác cách escape hoặc alias nhưng cùng ý nghĩa.

### 8.2. Import không dùng

Nếu generator thu thập import trước khi biết toàn bộ phần thân được sinh ra, một nhánh code có thể không sử dụng symbol như dự kiến. Có thể cần một bước finalize để loại bỏ import không còn được tham chiếu.

Một thiết kế tốt là `reference(symbol)` vừa ghi nhận yêu cầu vừa trả tên sử dụng; import cuối cùng chỉ chứa các symbol thực sự được render.

### 8.3. Import bị loại do dùng tên đầy đủ

Nếu conflict resolver quyết định dùng qualified name thay vì import, yêu cầu import tương ứng phải bị loại khỏi danh sách xuất. Nếu không, file có thể chứa import thừa.

### 8.4. Không loại import chỉ bằng tìm chuỗi

Một tên có thể xuất hiện trong comment, string literal hoặc tên thuộc tính mà không phải tham chiếu symbol. Phân tích AST hoặc các yêu cầu import đã thu thập chính xác hơn việc tìm chuỗi trong văn bản đầu ra.

## 9. Import theo nhóm và thứ tự ổn định

Import manager thường cần tạo import section dễ đọc và ổn định.

Ví dụ Java:

```java
import java.time.Instant;
import java.util.List;

import com.acme.billing.Invoice;
import com.acme.crm.Customer;
```

Các nhóm có thể được phân tách bằng dòng trống:

- Import chuẩn của platform hoặc standard library.
- Import thư viện bên ngoài.
- Import nội bộ của project.

Đây là quy ước phổ biến, không phải quy tắc bắt buộc của mọi ngôn ngữ.

### 9.1. Sắp xếp alphabetically

Trong mỗi nhóm, có thể sắp xếp theo qualified name hoặc theo module path. Quy tắc cần nhất quán để hai lần sinh mã từ cùng đầu vào tạo import section giống nhau.

### 9.2. Nhóm theo package

Một số dự án nhóm theo package hoặc prefix:

```java
import java.time.*;
import java.util.*;

import org.example.json.JsonReader;

import com.acme.domain.Customer;
```

Wildcard import có các trade-off riêng; không nên tự động chuyển sang wildcard chỉ để giảm số dòng import trừ khi chính sách backend cho phép.

### 9.3. Deterministic output

Đầu ra xác định (*deterministic output*) có nghĩa cùng source, compiler version, target configuration và dependency metadata tạo ra cùng import list và thứ tự import.

Không nên phụ thuộc vào:

- Thứ tự duyệt map không được đảm bảo.
- Thứ tự file system.
- Thời điểm task chạy song song hoàn tất.
- Hash set iteration order.
- Thứ tự import request phát sinh từ plugin không ổn định.

Có thể thu thập vào set rồi sắp xếp theo comparator rõ ràng trước khi render.

## 10. Wildcard import và import toàn bộ

Một số ngôn ngữ cho phép import tất cả symbol trong package hoặc module.

Ví dụ Java:

```java
import java.util.*;
```

Python:

```python
from package.module import *
```

TypeScript có thể import namespace:

```typescript
import * as models from "./models";
```

Những cú pháp này không hoàn toàn tương đương nhau. Wildcard có thể đưa nhiều tên vào phạm vi, còn namespace import thường tạo một đối tượng namespace để truy cập thành viên.

### 10.1. Ưu điểm

- Giảm số dòng import.
- Có thể tiện khi dùng nhiều symbol từ cùng một module.
- Có thể phù hợp với quy ước package hoặc module của dự án.

### 10.2. Nhược điểm

- Nguồn gốc của tên đơn giản khó nhìn thấy.
- Dễ phát sinh xung đột khi package bổ sung symbol mới.
- Công cụ có thể khó xác định import nào thực sự cần thiết.
- Mã sinh ra có thể thay đổi ý nghĩa khi dependency được nâng cấp.

### 10.3. Chính sách wildcard

Backend có thể cung cấp cấu hình:

```text
imports {
    wildcard = never
    groupStandardLibraryFirst = true
    sort = qualifiedName
}
```

Đây là cấu hình minh họa. Nhiều generator nên mặc định import tường minh vì nó thể hiện dependency rõ và tạo đầu ra dễ dự đoán. Nếu hỗ trợ wildcard, cần đặt quy tắc cụ thể khi nào được dùng.

## 11. Import tĩnh và import thành phần

Một số ngôn ngữ cho phép import thành phần tĩnh như hàm hoặc hằng số thay vì chỉ import kiểu hoặc module.

Java:

```java
import static java.lang.Math.max;
```

Khi đó mã có thể gọi `max(a, b)` thay vì `Math.max(a, b)`.

TypeScript:

```typescript
import { parse, stringify } from "./json-utils";
```

Import manager cần biết target symbol là type, function hay value để sinh đúng cú pháp. Nếu hai hàm cùng tên từ hai module, conflict resolver có thể cần alias hoặc namespace import.

### 11.1. Static import và xung đột hàm

Hai module có thể export hàm cùng tên `parse`. Nếu cả hai được import vào cùng scope, lời gọi `parse(...)` có thể mơ hồ hoặc không hợp lệ. Dùng alias hoặc truy cập qua namespace có thể làm rõ nguồn.

### 11.2. Import type-only

Một số ngôn ngữ phân biệt import chỉ dùng trong hệ thống kiểu với import cần tồn tại ở runtime. TypeScript hỗ trợ:

```typescript
import type { Customer } from "./models";
```

Nếu generator chỉ dùng `Customer` trong annotation kiểu, nó có thể sinh type-only import. Nếu symbol được dùng như giá trị runtime, cần import theo dạng phù hợp.

Phân loại này đặc biệt quan trọng khi target compiler loại bỏ type ở runtime hoặc khi module loader phân biệt type và value.

## 12. Import và vòng đời module

Import có thể ảnh hưởng cách runtime nạp module, khởi tạo thành phần và xử lý chu trình module. Điều này khác với import chỉ phục vụ biên dịch.

### 12.1. Compile-time import

Một import có thể chỉ giúp compiler phân giải tên hoặc kiểu. Nó có thể bị loại bỏ hoàn toàn khỏi mã runtime nếu không cần.

### 12.2. Runtime import

Một import có thể khiến runtime nạp module hoặc đánh giá mã khởi tạo. Khi đó, thứ tự import hoặc chu trình module có thể ảnh hưởng hành vi.

### 12.3. Type-only và value import

Trong target có type/value distinction, import manager cần xác định symbol được dùng ở đâu. Một import chỉ phục vụ type checking có thể không cần phát sinh lệnh nạp module.

### 12.4. Tránh thay đổi ngữ nghĩa khi gộp import

Không nên gộp hoặc đổi thứ tự import nếu target language quy định import có tác dụng phụ khi module được đánh giá. Việc sắp xếp import alphabetically chỉ an toàn khi thứ tự import không ảnh hưởng ngữ nghĩa hoặc khi target/backend bảo đảm điều đó.

## 13. Import nội bộ và symbol được sinh trong cùng output

Không phải mọi target symbol đều cần import. Một kiểu có thể được định nghĩa ngay trong tệp đang sinh hoặc trong cùng package/module.

Ví dụ:

```java
package com.acme.generated;

public class Customer {
}

class CustomerService {
    Customer find() { ... }
}
```

`CustomerService` không cần import `Customer` vì kiểu nằm trong cùng package và có thể truy cập theo quy tắc Java.

Import manager cần biết context của output file:

- Package hoặc module hiện tại.
- Các symbol được định nghĩa trong cùng file.
- Các symbol thuộc cùng package.
- Các symbol nested hoặc được export qua namespace.
- Các symbol mặc định có sẵn trong target language.

### 13.1. Default imports

Một số ngôn ngữ hoặc framework tự động đưa một số package/symbol vào phạm vi. Backend có thể đánh dấu chúng là implicit import để không phát khai báo dư.

### 13.2. Nested types

Một kiểu lồng nhau có thể có tên đầy đủ dạng `Outer.Inner`. Target language có thể cho phép import nested type riêng hoặc yêu cầu tham chiếu qua outer type. Import manager phải dùng metadata và quy tắc backend.

### 13.3. Module-local symbols

Nếu output file nằm trong cùng module, có thể không cần import nhưng vẫn cần bảo đảm visibility và name resolution đúng.

## 14. Import theo target language

Một import manager tổng quát không nên hard-code một cú pháp duy nhất. Backend cần cung cấp chiến lược import riêng.

### 14.1. Java

Java import class hoặc static member:

```java
import java.time.Instant;
import java.util.List;
import static java.util.Collections.emptyList;
```

Java không hỗ trợ alias import tổng quát. Khi có hai kiểu cùng tên đơn giản, thường cần dùng tên đầy đủ cho ít nhất một kiểu. Import cùng package và một số package mặc định có quy tắc riêng.

### 14.2. Kotlin

Kotlin hỗ trợ alias:

```kotlin
import java.util.Date as UtilDate
import java.sql.Date as SqlDate
```

Kotlin cũng có import top-level function và property, nên import manager cần phân biệt package member với class member.

### 14.3. TypeScript / JavaScript

TypeScript có named import, default import, namespace import và type-only import:

```typescript
import DefaultClient from "./client";
import { Customer, Invoice as BillingInvoice } from "./models";
import type { RequestContext } from "./context";
import * as Validation from "./validation";
```

Module specifier thường là đường dẫn tương đối, package name hoặc alias path theo cấu hình module resolver. Generator cần biết output path để tạo relative import đúng.

### 14.4. Python

Python có:

```python
import datetime
from datetime import datetime as DateTime
from package.models import Customer
```

Import có thể thực thi logic nạp module ở runtime. Generator cần tránh tạo chu trình hoặc import có tác dụng phụ ngoài dự kiến, đặc biệt khi module khởi tạo nhiều trạng thái.

### 14.5. C#

C# dùng `using`:

```csharp
using System;
using System.Collections.Generic;
using CustomerModel = Acme.Crm.Customer;
```

C# hỗ trợ alias namespace và kiểu. Một số phiên bản hỗ trợ global using hoặc using static, vì vậy backend có thể có tùy chọn theo version target.

### 14.6. Không áp đặt quy tắc chung lên mọi ngôn ngữ

Một backend có thể hỗ trợ alias, backend khác không. Một target có thể phân biệt type/value import, target khác không. Import manager nên cung cấp abstraction chung ở mức symbol request và để từng backend quyết định cú pháp, khả năng và giới hạn cụ thể.

## 15. Đường dẫn import tương đối và tuyệt đối

Một số ngôn ngữ, đặc biệt JavaScript/TypeScript, thường dùng module specifier tương đối:

```typescript
import { Customer } from "../models/customer";
```

Một module cũng có thể được tham chiếu bằng package name hoặc alias:

```typescript
import { Customer } from "@domain/customer";
```

### 15.1. Tính đường dẫn từ output file

Generator cần biết vị trí tệp đầu ra và vị trí module đích để tạo relative path. Ví dụ, nếu output được sinh vào `src/generated/api.ts`, đường dẫn đến `src/models/customer.ts` khác với khi output nằm ở `src/generated/v2/api.ts`.

### 15.2. Chuẩn hóa separator

Module specifier thường dùng `/` bất kể hệ điều hành. Không nên lấy trực tiếp đường dẫn Windows có `\\` để ghi vào import TypeScript nếu target yêu cầu slash chuẩn.

### 15.3. Phần mở rộng tệp

Một số cấu hình yêu cầu import có phần mở rộng `.js`, `.ts` hoặc không có extension. Generator cần tuân theo module resolution strategy của target project.

### 15.4. Alias path và project configuration

Alias như `@domain/*` chỉ hợp lệ nếu compiler hoặc bundler được cấu hình tương ứng. Code generator không nên tự tạo alias tùy ý mà không cập nhật hoặc kiểm tra cấu hình project.

## 16. Import và module system

Các target language có thể dùng những module system khác nhau. Import manager cần phân biệt package path, module name và symbol path.

### 16.1. Package-based system

Trong Java, package thường tạo namespace cho class. Import một class dùng tên package và class.

### 16.2. File-based module system

Trong JavaScript/TypeScript, module thường gắn với tệp hoặc package entry point. Đường dẫn import phụ thuộc cấu trúc output và cấu hình resolver.

### 16.3. Namespace-based system

Một DSL hoặc target language có thể tổ chức symbol theo namespace lồng nhau. Import có thể tham chiếu namespace, symbol hoặc một nhóm thành phần.

### 16.4. Module visibility và export

Import manager cần kiểm tra symbol có được export hay không. Việc một symbol tồn tại trong package không có nghĩa module khác có thể import nó.

## 17. Quản lý import trong nhiều tệp được sinh

Một DSL có thể sinh nhiều tệp từ cùng một mô hình. Mỗi tệp có tập import riêng.

Ví dụ:

```text
generated/
├── Customer.java
├── Invoice.java
└── InvoiceService.java
```

`Customer.java` có thể cần `Instant`; `Invoice.java` cần `BigDecimal` và `Customer`; `InvoiceService.java` cần `Invoice` và `List`.

### 17.1. Import scope theo output file

Import trong Java hoặc TypeScript thường thuộc phạm vi tệp. Một import trong `Invoice.java` không tự động có hiệu lực trong `InvoiceService.java`.

Do đó, mỗi output file cần một import manager hoặc một context import độc lập.

### 17.2. Chia sẻ registry, không chia sẻ import list

Các file generator có thể dùng chung symbol registry hoặc target mapping, nhưng danh sách import cuối cùng phải được tính theo những symbol thực sự được tham chiếu trong từng file.

### 17.3. Sinh theo thứ tự bất kỳ

Nếu file generation chạy song song, import manager của mỗi file không nên phụ thuộc vào thứ tự file khác được sinh. Điều này giúp kết quả ổn định và tránh trạng thái chia sẻ gây race condition.

## 18. Import manager và template-based code generation

Một số generator dùng template để sinh mã. Import có thể được quản lý bằng một phần context được template truy cập.

Ví dụ template giả định:

```text
{{#each imports}}
import {{this}};
{{/each}}

public class {{className}} {
    {{#each fields}}
    private {{typeName}} {{name}};
    {{/each}}
}
```

Generator cần thu thập import trước khi render phần header, hoặc dùng một writer có thể ghi nhận symbol khi render rồi finalize header ở bước sau.

### 18.1. Hai lượt render

Một chiến lược là:

1. Duyệt model để thu thập tất cả target symbol cần thiết.
2. Tính import decision và alias.
3. Render header và phần thân bằng cùng bảng quyết định.

Điều này tránh tình trạng template ghi `Instant` nhưng import manager lại quyết định dùng tên đầy đủ hoặc alias khác.

### 18.2. Symbol handle thay vì chuỗi

Template nên nhận một handle hoặc đối tượng target symbol, rồi gọi resolver để lấy tên tham chiếu. Nếu template tự nối package và tên class bằng chuỗi, logic conflict resolution sẽ bị bỏ qua.

## 19. Import manager trong code generator hướng đối tượng

Một API đơn giản có thể như sau:

```java
interface ImportManager {
    TypeReference reference(TargetType type);
    ExpressionReference reference(TargetSymbol symbol);
    List<ImportDeclaration> finalizeImports();
}
```

Generator sử dụng:

```java
TypeReference instant = imports.reference(TargetTypes.INSTANT);
writer.write("private " + instant.render() + " createdAt;");
```

Sau khi sinh body:

```java
List<ImportDeclaration> declarations = imports.finalizeImports();
```

Trong triển khai thực tế, `TypeReference` có thể là một object có render method hoặc một symbol handle được resolve khi render. Tránh trả về chuỗi quá sớm nếu conflict resolution còn có thể thay đổi sau khi phát hiện symbol trùng tên.

### 19.1. Trạng thái collect và finalize

Import manager thường có hai giai đoạn:

- **Collecting:** nhận yêu cầu symbol.
- **Finalized:** đã quyết định tên tham chiếu, alias và import list.

Sau finalize, không nên tiếp tục thêm yêu cầu mới nếu việc đó có thể làm thay đổi quyết định đã dùng trong phần thân. Có thể dùng hai pass hoặc cơ chế deferred reference để tránh vấn đề.

### 19.2. Reset theo file

Nếu một instance được tái sử dụng cho nhiều output file, cần reset đầy đủ trạng thái hoặc tạo context mới cho mỗi file. Nếu không, import của file trước có thể rò sang file sau.

## 20. Ví dụ thuật toán import manager

Một thuật toán khái niệm:

```text
reference(targetSymbol):
    requests.add(targetSymbol)
    return ReferenceHandle(targetSymbol)

finalize(currentFileContext):
    grouped = group requests by simpleName

    for each group:
        if group has one symbol:
            choose simple name and import if needed
        else:
            resolve conflict using alias or qualified name

    remove implicit and same-package imports
    deduplicate imports
    sort imports deterministically

    return decisions and import declarations
```

Trong hệ thống thực tế, `reference` có thể được gọi trước khi biết toàn bộ tập symbol. Vì vậy, `ReferenceHandle` nên trì hoãn việc render tên cho đến khi `finalize` đã quyết định cách tham chiếu.

### 20.1. Pseudocode chi tiết hơn

```text
finalize(requests, fileContext, targetRules):
    unique = deduplicateBySymbolIdentity(requests)
    byName = groupBySimpleName(unique)
    decisions = emptyMap()
    imports = emptySet()

    for group in byName:
        if group.size == 1:
            symbol = group.onlyElement
            if targetRules.canUseSimpleName(symbol, fileContext):
                decisions[symbol] = simpleReference(symbol)
                if targetRules.requiresImport(symbol, fileContext):
                    imports.add(importFor(symbol))
            else:
                decisions[symbol] = qualifiedReference(symbol)
        else:
            resolveGroupConflict(group, fileContext, targetRules,
                decisions, imports)

    imports = removeImplicitImports(imports, fileContext)
    imports = normalizeAndSort(imports, targetRules)
    return ImportPlan(decisions, imports)
```

Đây là thuật toán minh họa. Một target language có thể cần xử lý overload, extension method, default export, namespace import hoặc type/value namespace riêng.

## 21. Xử lý import không hợp lệ

Import manager không chỉ render chuỗi. Nó còn cần báo lỗi nếu target symbol không thể được tham chiếu hợp lệ.

Các tình huống thường gặp:

- Symbol không tồn tại trong target mapping.
- Package hoặc module không được export.
- Dependency target chưa được khai báo.
- Alias không hợp lệ theo grammar target.
- Hai symbol không thể phân biệt trong target namespace.
- Đường dẫn tương đối không thể tính hoặc trỏ ra ngoài vùng được phép.
- Target version không hỗ trợ cú pháp import cần dùng.

Ví dụ, DSL yêu cầu sinh một annotation chỉ có ở Java version mới, nhưng target configuration đang chọn Java version cũ. Backend nên phát diagnostic rõ thay vì tạo import đến một API không tồn tại.

### 21.1. Diagnostic tại symbol sử dụng

Nếu import không thể tạo vì symbol không được export, diagnostic nên gắn với nơi DSL sử dụng symbol đó hoặc nơi mapping target được khai báo.

### 21.2. Không âm thầm bỏ import lỗi

Nếu generator bỏ một import không hợp lệ nhưng vẫn sinh code tham chiếu tên ngắn, output sẽ có lỗi khó hiểu ở bước compile sau. Nên phát diagnostic hoặc dùng tên đầy đủ nếu điều đó giải quyết được vấn đề hợp lệ.

### 21.3. Lỗi cấu hình target

Nếu target language hoặc module system không được xác định, generator có thể không biết cách render import. Cần báo lỗi cấu hình ở giai đoạn chuẩn bị backend.

## 22. Tối ưu import và định dạng mã

Import manager có thể phối hợp với formatter hoặc style configuration.

Các tùy chọn có thể gồm:

- Nhóm standard library, external và internal.
- Sắp xếp alphabetically hoặc theo package.
- Dùng hoặc cấm wildcard.
- Giới hạn số import trước khi cân nhắc wildcard.
- Dòng trống giữa các nhóm.
- Thứ tự static import.
- Quy tắc alias.
- Quy tắc bỏ import không dùng.

### 22.1. Không trộn logic style với logic phân giải symbol

Import manager trước hết phải chọn đúng symbol và cách tham chiếu hợp lệ. Formatter hoặc import organizer có thể sắp xếp và định dạng kết quả sau đó. Không nên để quy tắc style làm thay đổi danh tính symbol được tham chiếu.

### 22.2. Tính idempotent

Một import organizer tốt nên có tính idempotent: chạy nhiều lần trên cùng nội dung không tiếp tục thay đổi thứ tự hoặc cách nhóm import.

### 22.3. Giảm diff không cần thiết

Nếu thứ tự import thay đổi ngẫu nhiên giữa các lần build, code review sẽ có nhiều diff nhiễu. Sắp xếp ổn định và quy tắc nhóm rõ ràng giúp diff chỉ phản ánh thay đổi thật.

## 23. Import và generated code có thể được chạy lại

Code generation thường được thực hiện nhiều lần. Import manager phải tạo kết quả giống nhau khi source và cấu hình không đổi.

### 23.1. Không giữ trạng thái giữa các lần sinh ngoài ý muốn

Một instance manager không nên giữ import từ lần sinh file trước nếu file mới là output độc lập. Mỗi lần generation cần context rõ.

### 23.2. Không phụ thuộc thứ tự traversal

Nếu visitor duyệt field theo thứ tự khác, import list vẫn phải được chuẩn hóa giống nhau. Thu thập vào set và sort ở bước cuối là một cách thường dùng.

### 23.3. Ổn định alias

Nếu alias được tạo dựa trên thứ tự gặp symbol, chỉ cần traversal đổi là alias có thể đổi. Nên tạo alias từ quy tắc xác định như tên package, module prefix hoặc bảng cấu hình, rồi giải quyết trùng bằng quy tắc ổn định.

### 23.4. Cache import plan

Nếu cache import plan, cache key cần tính đến target language version, package mapping, output file context, symbol set và import style options. Cùng tập symbol trong hai output file khác nhau có thể cần relative import path khác nhau.

## 24. Kiểm thử quản lý import

Import manager cần được kiểm thử ở cấp đơn vị và qua output code thực tế.

### 24.1. Kiểm thử import đơn

Với một target symbol không xung đột, xác nhận manager tạo đúng import và trả tên tham chiếu đúng.

Ví dụ:

```text
Request: java.time.Instant
Expected import: java.time.Instant
Expected reference: Instant
```

### 24.2. Kiểm thử import trùng

Yêu cầu cùng một symbol từ nhiều node và xác nhận chỉ có một import.

### 24.3. Kiểm thử xung đột tên

Yêu cầu cả `java.util.Date` và `java.sql.Date`, xác nhận manager dùng alias hoặc qualified name theo chính sách Java backend.

### 24.4. Kiểm thử cùng package và default import

Đảm bảo manager không sinh import thừa khi symbol có thể được truy cập theo quy tắc mặc định của target language.

### 24.5. Kiểm thử type-only và runtime import

Với TypeScript, xác nhận symbol chỉ dùng trong annotation tạo type-only import khi cấu hình cho phép, còn symbol được dùng ở runtime tạo import phù hợp.

### 24.6. Kiểm thử relative path

Sinh hai tệp ở các thư mục khác nhau và xác nhận module specifier tương đối được tính từ đúng output location.

### 24.7. Kiểm thử tính xác định

Chạy generation nhiều lần với cùng đầu vào nhưng thay đổi thứ tự traversal nội bộ. Import list và nội dung output cần giữ ổn định.

### 24.8. Compile output

Một kiểm thử tích hợp có thể đưa mã sinh ra qua compiler của target language để phát hiện import thiếu, sai package, alias không hợp lệ hoặc module specifier sai.

## 25. Ví dụ tổng hợp: sinh Java từ DSL

Giả sử DSL:

```text
namespace shop {
    model Invoice {
        id: UUID
        createdAt: Timestamp
        total: Money
        customer: Customer
    }
}
```

Backend Java có mapping:

| Kiểu DSL | Target type |
|---|---|
| `UUID` | `java.util.UUID` |
| `Timestamp` | `java.time.Instant` |
| `Money` | `com.acme.money.Money` |
| `Customer` | `com.acme.crm.Customer` |

Import manager thu thập bốn target symbol. Nếu không có xung đột, output có thể là:

```java
package com.acme.generated.shop;

import java.time.Instant;
import java.util.UUID;

import com.acme.crm.Customer;
import com.acme.money.Money;

public class Invoice {
    private UUID id;
    private Instant createdAt;
    private Money total;
    private Customer customer;
}
```

Nếu trong cùng tệp cần cả `java.sql.Timestamp` và một kiểu `Timestamp` khác, manager phải xử lý conflict theo quy tắc Java. Nó có thể dùng tên đầy đủ cho một kiểu, hoặc điều chỉnh mapping để tránh tên ngắn trùng.

Quy trình tổng quát:

1. Frontend phân giải các kiểu DSL.
2. Java backend ánh xạ kiểu DSL sang target symbol.
3. Code generator yêu cầu reference cho từng target symbol.
4. Import manager thu thập và giải quyết tên.
5. Generator render class body bằng các reference đã quyết định.
6. Import manager render import section.
7. Java compiler kiểm tra mã đầu ra.

## 26. Ví dụ tổng hợp: sinh TypeScript từ DSL

Giả sử DSL khai báo:

```text
model Invoice {
    customer: Customer
    createdAt: Timestamp
}
```

Backend TypeScript ánh xạ:

```text
Customer -> ./customer.Customer
Timestamp -> Date
```

Mã sinh ra có thể là:

```typescript
import type { Customer } from "./customer";

export interface Invoice {
    customer: Customer;
    createdAt: Date;
}
```

`Date` là global type/value có sẵn trong môi trường TypeScript/JavaScript nên có thể không cần import. `Customer` chỉ dùng làm kiểu nên backend có thể chọn `import type`.

Nếu `Customer` được dùng trong code runtime:

```typescript
const customer = new Customer();
```

backend cần import value tương ứng, không thể chỉ dùng type-only import.

## 27. Những sai lầm thường gặp

**Tạo import bằng cách quét chuỗi đầu ra.** Chuỗi giống tên symbol có thể nằm trong comment hoặc literal. Nên thu thập reference từ AST/IR hoặc generator API.

**Chỉ lưu tên đơn giản.** Hai package có thể có symbol trùng tên. Cần giữ qualified name hoặc symbol identity.

**Nhầm import với dependency declaration.** Import trong mã nguồn không tự thêm thư viện vào build configuration.

**Thêm import ngay khi gặp symbol mà không xử lý xung đột toàn cục.** Một symbol được dùng sớm có thể được đặt tên ngắn, nhưng về sau phát hiện symbol khác trùng tên. Cần finalize sau khi thu thập đủ yêu cầu hoặc dùng reference handle trì hoãn.

**Dùng wildcard để che xung đột.** Wildcard không đảm bảo giải quyết được mơ hồ và có thể làm mã khó bảo trì.

**Không phân biệt type-only và runtime import.** Điều này có thể làm module loader hoặc target compiler báo lỗi.

**Dùng relative path từ thư mục nguồn thay vì thư mục output.** Module specifier phải được tính theo vị trí tệp sinh ra và quy tắc target resolver.

**Không tính đến symbol cùng package hoặc default import.** Điều này tạo import thừa hoặc import không hợp lệ.

**Sắp xếp dựa vào thứ tự collection không ổn định.** Kết quả build có thể thay đổi không cần thiết giữa các lần chạy.

**Chia sẻ import list giữa nhiều output file.** Import scope thường thuộc từng tệp; một tệp không tự kế thừa import của tệp khác.

**Tự tạo alias theo thứ tự traversal.** Alias có thể đổi giữa các lần build. Cần quy tắc tạo alias xác định.

## 28. Ghi nhớ

- Quản lý import là xác định, giải quyết và render các tham chiếu đến symbol của ngôn ngữ đích trong mã được sinh.
- Import khác dependency declaration: một cái phục vụ name resolution trong source, cái kia quản lý thư viện hoặc module cho build/runtime.
- Code generator nên yêu cầu target symbol qua import manager thay vì tự nối tên package và tên class.
- Import manager cần giữ qualified name hoặc symbol identity để phân biệt symbol trùng tên.
- Khi xung đột, backend có thể dùng alias hoặc qualified name theo khả năng của target language.
- Import trùng cần được khử; import không dùng hoặc implicit import cần được xử lý theo quy tắc target.
- Nhóm và sắp xếp import ổn định giúp output dễ đọc và giảm diff không cần thiết.
- Wildcard, static import, namespace import và type-only import có ngữ nghĩa khác nhau giữa các ngôn ngữ.
- Mỗi output file thường cần import context riêng; relative path phải được tính từ vị trí file đầu ra.
- Import plan cần tính đến target version, module system, package mapping và style options.
- Import manager cần tạo output xác định, kiểm tra conflict và phát diagnostic khi symbol không thể được tham chiếu hợp lệ.

## 29. Câu hỏi tự kiểm tra

1. Quản lý import trong code generation giải quyết vấn đề gì?
2. Phân biệt import trong mã nguồn với dependency declaration của build system.
3. Vì sao import manager nên làm việc với target symbol thay vì chỉ tên kiểu DSL?
4. Tại sao cần lưu qualified name hoặc symbol identity thay vì chỉ simple name?
5. Khi hai symbol có cùng simple name, backend có thể giải quyết xung đột bằng những cách nào?
6. Vì sao import manager nên thu thập yêu cầu trước khi finalize danh sách import?
7. Import trùng và import không dùng được xử lý như thế nào?
8. Tại sao thứ tự import cần ổn định giữa các lần sinh mã?
9. Wildcard import có ưu điểm và rủi ro nào?
10. Phân biệt type-only import với runtime import trong TypeScript.
11. Khi sinh nhiều tệp TypeScript, relative import path cần được tính từ đâu?
12. Vì sao mỗi output file thường cần import manager hoặc import context riêng?
13. Những trường nào cần có trong cache key nếu muốn cache một import plan?
14. Hãy mô tả các bước import manager thực hiện khi backend Java cần cả `java.util.Date` và `java.sql.Date`.

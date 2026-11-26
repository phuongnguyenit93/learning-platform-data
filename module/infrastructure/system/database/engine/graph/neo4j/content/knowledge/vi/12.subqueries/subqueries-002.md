# EXISTS để kiểm tra sự tồn tại của mẫu hoặc kết quả con

> **Chương:** Truy vấn con  
> **Hệ quản trị:** Neo4j — property graph, truy vấn bằng Cypher.  
> **Mục tiêu:** Biết dùng `EXISTS { ... }` để kiểm tra có ít nhất một mẫu quan hệ hoặc hàng kết quả thỏa điều kiện, dùng `NOT EXISTS { ... }` để tìm trường hợp không thỏa, và tránh nhân bản hàng dữ liệu khi chỉ cần câu trả lời đúng/sai.

## 1. Bài toán: hỏi “có tồn tại không?” trên đồ thị

Trong property graph, mỗi **node** biểu diễn một thực thể, mỗi **relationship** biểu diễn một liên kết và có thể mang thuộc tính. Những câu hỏi rất thường gặp là:

- Người dùng **có theo dõi ai** không?
- Một người **có theo dõi người đang hoạt động** không?
- Có tồn tại **đường đi hai bước** từ người A tới người B không?
- Có người mà A đã theo dõi nhưng **chưa chặn** không?
- Một node **có bất kỳ quan hệ nào** đáp ứng điều kiện về thời gian hoặc thuộc tính không?

Nếu chỉ cần biết **có ít nhất một kết quả**, không cần lấy toàn bộ các node/relationship khớp mẫu, dùng **existential subquery** (*truy vấn con kiểm tra sự tồn tại*):

```cypher
MATCH (u:User)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(:User)
}
RETURN u;
```

`EXISTS { ... }` là một **biểu thức Boolean** trong Cypher:

- Trả `true` nếu truy vấn con có **ít nhất một hàng** đáp ứng điều kiện.
- Trả `false` nếu truy vấn con có **0 hàng**.
- Có thể đặt trong `WHERE`, biểu thức `RETURN`, `CASE` và kết hợp với `AND`, `OR`, `NOT`.
- **Không trả các node/relationship** của truy vấn con ra truy vấn ngoài, cũng **không nhân số hàng ngoài** theo số mẫu trùng khớp.

Điều kiện cốt lõi là **có hàng kết quả hay không**; không phải giá trị của các cột ở hàng đó là `true`, `false` hay `null`.

## 2. Dữ liệu mẫu để chạy theo bài

Ví dụ bên dưới mô phỏng một mạng xã hội nhỏ. Mỗi node `:ExistsDemoUser` có `id`, `name` và `active`. Quan hệ `:FOLLOWS` có thuộc tính `since` biểu diễn năm bắt đầu theo dõi; `:BLOCKS` biểu diễn việc chặn.

```text
                    FOLLOWS (2022)
          An --------------------------> Bình
          |                                |
          | FOLLOWS (2020)                 | FOLLOWS (2024)
          v                                v
         Chi <-----------------------------+
          |
          | FOLLOWS (2023)
          +-----------------------------> An

          An --BLOCKS-------------------> Chi

         Dũng  (không có FOLLOWS)
```

Trạng thái `active`: **An = true**, **Bình = true**, **Chi = false**, **Dũng = true**.

Chạy đoạn sau **một lần** trên database thử nghiệm. Mỗi node dùng một `id` riêng; `MERGE` giúp việc chạy lại đoạn ví dụ không cố ý tạo thêm một đường quan hệ giống hệt giữa cùng hai node nếu đồ thị ban đầu sạch.

```cypher
MERGE (an:ExistsDemoUser {id: 'an'})
SET an.name = 'An', an.active = true
MERGE (binh:ExistsDemoUser {id: 'binh'})
SET binh.name = 'Bình', binh.active = true
MERGE (chi:ExistsDemoUser {id: 'chi'})
SET chi.name = 'Chi', chi.active = false
MERGE (dung:ExistsDemoUser {id: 'dung'})
SET dung.name = 'Dũng', dung.active = true
WITH an, binh, chi
MERGE (an)-[ab:FOLLOWS]->(binh)
SET ab.since = 2022
MERGE (an)-[ac:FOLLOWS]->(chi)
SET ac.since = 2020
MERGE (binh)-[bc:FOLLOWS]->(chi)
SET bc.since = 2024
MERGE (chi)-[ca:FOLLOWS]->(an)
SET ca.since = 2023
MERGE (an)-[:BLOCKS]->(chi);
```

Trong toàn bộ bài, kết quả minh họa giả định database thử nghiệm chỉ có **bốn node và các quan hệ trên** mang nhãn/kiểu đã nêu. Nếu dữ liệu của bạn có thêm node hoặc liên kết cùng loại, tập kết quả có thể khác.

## 3. Dùng `EXISTS { MATCH ... }` để kiểm tra mẫu quan hệ

### 3.1. Tìm người có ít nhất một quan hệ đi ra

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(:ExistsDemoUser)
}
RETURN u.name AS person
ORDER BY person;
```

| person |
|---|
| An |
| Bình |
| Chi |

Đối với `An`, truy vấn con tìm thấy **hai** quan hệ theo dõi, nhưng `EXISTS` chỉ trả một giá trị Boolean nên truy vấn ngoài vẫn có **một hàng cho An**. `Dũng` không có `FOLLOWS` đi ra nên bị loại.

Có thể viết **dạng mẫu ngắn** mà không cần khai báo `MATCH` cho tình huống đơn giản:

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  (u)-[:FOLLOWS]->(:ExistsDemoUser)
}
RETURN u.name AS person
ORDER BY person;
```

Hai ví dụ trên diễn đạt cùng câu hỏi. Khi muốn thêm điều kiện trên node, relationship hoặc nhiều bước khớp mẫu, dạng có `MATCH` và `WHERE` thường dễ mở rộng hơn.

### 3.2. `EXISTS` hoạt động thế nào theo từng hàng?

`MATCH (u:ExistsDemoUser)` tạo bốn hàng đầu vào tương ứng bốn người. Với **mỗi hàng**, `EXISTS` thử tìm mẫu có gắn với `u` của hàng đó.

| Giá trị `u` từ ngoài | Số mẫu `FOLLOWS` khớp bên trong | Giá trị `EXISTS` | Hàng ngoài được giữ khi dùng `WHERE`? |
|---|---:|---|---|
| An | 2 | `true` | Có |
| Bình | 1 | `true` | Có |
| Chi | 1 | `true` | Có |
| Dũng | 0 | `false` | Không |

Đây là **correlated subquery**: truy vấn con phụ thuộc vào biến `u` được xác định ở truy vấn ngoài. Mặc dù điều kiện được kiểm tra theo từng hàng, cách thực thi vật lý do bộ lập kế hoạch của Neo4j quyết định; không nên hiểu bảng trên là cam kết rằng Neo4j luôn phải duyệt tuần tự mọi mẫu.

## 4. Lọc theo thuộc tính node và relationship

### 4.1. Có theo dõi người đang hoạt động?

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE v.active = true
}
RETURN u.name AS person
ORDER BY person;
```

| person |
|---|
| An |
| Chi |

Giải thích:

- `An` theo dõi `Bình`, mà `Bình.active = true`.
- `Chi` theo dõi `An`, mà `An.active = true`.
- `Bình` chỉ theo dõi `Chi` đang không hoạt động.
- `Dũng` không theo dõi ai.

Điều kiện `WHERE v.active = true` được đặt **bên trong** `EXISTS`, vì nó kiểm tra thuộc tính của node `v` vừa được tìm thấy. Biến `v` chỉ tồn tại trong truy vấn con.

### 4.2. Kết hợp điều kiện trên quan hệ và node

Tìm người có quan hệ theo dõi bắt đầu **từ năm 2023**, và người được theo dõi đang hoạt động:

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[r:FOLLOWS]->(v:ExistsDemoUser)
  WHERE r.since >= 2023
    AND v.active = true
}
RETURN u.name AS person
ORDER BY person;
```

Kết quả chỉ có **Chi**, vì quan hệ `Chi -[:FOLLOWS {since: 2023}]-> An` khớp cả hai điều kiện. Quan hệ `Bình -> Chi` có năm 2024 nhưng `Chi.active = false`.

Trong ứng dụng Java Driver hoặc Spring Data Neo4j, nên truyền ngưỡng năm bằng tham số thay vì ghép chuỗi truy vấn:

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[r:FOLLOWS]->(v:ExistsDemoUser)
  WHERE r.since >= $minYear
    AND v.active = true
}
RETURN u.name AS person
ORDER BY person;
```

Với `minYear = 2023`, kết quả giống ví dụ trước. Tham số giúp tái sử dụng truy vấn và tránh nối trực tiếp dữ liệu người dùng vào cú pháp Cypher.

## 5. `NOT EXISTS`: kiểm tra không tồn tại mẫu

Để tìm **người không theo dõi bất kỳ ai**, phủ định biểu thức `EXISTS`:

```cypher
MATCH (u:ExistsDemoUser)
WHERE NOT EXISTS {
  MATCH (u)-[:FOLLOWS]->(:ExistsDemoUser)
}
RETURN u.name AS person
ORDER BY person;
```

Kết quả chỉ có **Dũng**.

Phân biệt hai câu hỏi rất dễ nhầm:

| Điều kiện | Ý nghĩa | Kết quả trong dữ liệu mẫu |
|---|---|---|
| `NOT EXISTS { MATCH (u)-[:FOLLOWS]->(v) }` | Người này không theo dõi ai. | Dũng |
| `NOT EXISTS { MATCH (u)-[:FOLLOWS]->(v) WHERE v.active = true }` | Người này không theo dõi ai **đang hoạt động**. Có thể họ vẫn theo dõi người không hoạt động. | Bình, Dũng |

Câu truy vấn cho điều kiện thứ hai:

```cypher
MATCH (u:ExistsDemoUser)
WHERE NOT EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE v.active = true
}
RETURN u.name AS person
ORDER BY person;
```

**Bình** có quan hệ `FOLLOWS`, nhưng **không có** quan hệ `FOLLOWS` nào dẫn tới người đang hoạt động. Vì vậy Bình thỏa câu hỏi thứ hai nhưng không thỏa câu hỏi thứ nhất.

Đây là cách diễn đạt phủ định chính xác trong các bài toán như “khách hàng chưa có đơn thành công”, “máy chủ chưa có bản vá”, “tài khoản chưa có liên kết xác thực” hoặc “node không kết nối tới nhóm bị cấm”.

## 6. Kiểm tra kết quả truy vấn con phức tạp: nhiều bước và `EXISTS` lồng nhau

### 6.1. Có đường đi hai bước tới một node cụ thể?

Tìm người có thể đi tới node `Chi` qua **đúng hai** quan hệ `FOLLOWS`:

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(middle:ExistsDemoUser)
        -[:FOLLOWS]->(destination:ExistsDemoUser {id: 'chi'})
}
RETURN u.name AS person
ORDER BY person;
```

| person |
|---|
| An |
| Chi |

- `An -> Bình -> Chi`: có đường đi hai bước.
- `Chi -> An -> Chi`: có đường đi hai bước.
- `Bình -> Chi -> An`: không tới `Chi` sau hai bước.
- `Dũng`: không có đường đi.

Ở đây `EXISTS` kiểm tra **sự tồn tại của kết quả MATCH hai bước**, không trả đường đi đó ra ngoài. Nếu cần trả danh sách đường đi hoặc node trung gian, phải dùng `MATCH` thông thường hoặc `CALL` subquery phù hợp.

### 6.2. Kiểm tra “có theo dõi người nào mà mình chưa chặn”

Đây là tình huống dùng `EXISTS` **lồng nhau** để biểu diễn hai điều kiện liên quan đến **cùng node `v`**:

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE NOT EXISTS {
    MATCH (u)-[:BLOCKS]->(v)
  }
}
RETURN u.name AS person
ORDER BY person;
```

| person |
|---|
| An |
| Bình |
| Chi |

`An` theo dõi cả `Bình` và `Chi` nhưng chặn `Chi`; quan hệ `An -> Bình` vẫn khiến điều kiện đúng. `Bình` theo dõi `Chi` mà không chặn; `Chi` theo dõi `An` mà không chặn. `Dũng` không theo dõi ai.

**Cực kỳ quan trọng:** ở truy vấn con trong cùng, biến `v` đã được ràng buộc bởi `MATCH` ngay phía trên, nên kiểm tra chặn áp dụng cho **đúng người đang xét**. Hai kiểm tra tồn tại tách rời sẽ trả lời câu hỏi khác:

```cypher
// KHÁC NGHĨA: có theo dõi ai đó VÀ không chặn bất kỳ ai.
// Không bảo đảm người đang được theo dõi là người đang xét chặn.
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(:ExistsDemoUser)
}
AND NOT EXISTS {
  MATCH (u)-[:BLOCKS]->(:ExistsDemoUser)
}
RETURN u.name AS person;
```

Ví dụ thứ hai **loại An hoàn toàn**, bởi vì An có chặn Chi, mặc dù An vẫn theo dõi Bình mà không chặn Bình. Khi phát biểu bài toán có các từ “cùng người”, “cùng đơn hàng”, “cùng node đích”, phải dùng chung biến trong đúng phạm vi.

### 6.3. `AND` / `OR` với nhiều điều kiện tồn tại

Tìm người **đồng thời** có theo dõi ai đó **và** có chặn ai đó:

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(:ExistsDemoUser)
}
AND EXISTS {
  MATCH (u)-[:BLOCKS]->(:ExistsDemoUser)
}
RETURN u.name AS person;
```

Kết quả là **An**. Hai `EXISTS` kiểm tra hai điều kiện độc lập nhưng đều tương quan với `u` của hàng ngoài. Nếu cần “hoặc”, có thể thay `AND` bằng `OR`, thêm dấu ngoặc để làm rõ thứ tự đánh giá.

## 7. Phạm vi biến: khác `CALL` subquery ở điểm nào?

Đối với **`EXISTS { ... }`**, các biến đang ở scope bên ngoài **tự động khả dụng** bên trong subquery. Thông thường **không cần importing `WITH`** hay variable scope clause `CALL (u)`.

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE v.active = true
}
RETURN u.name AS person;
```

Tại đây:

- `u` được xác định bởi `MATCH` ngoài và được dùng bên trong.
- `v` được xác định bởi `MATCH` trong, chỉ dùng được bên trong.
- `EXISTS` cung cấp **true/false** cho biểu thức ngoài; **không xuất biến `v`**.

Ví dụ **sai** vì phạm vi biến:

```cypher
// SAI: v được tạo bên trong EXISTS, không nằm trong scope của RETURN ngoài.
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
}
RETURN u.name, v.name;
```

Nếu cần cả `u.name` và `v.name`, hãy dùng `MATCH` trực tiếp:

```cypher
MATCH (u:ExistsDemoUser)-[:FOLLOWS]->(v:ExistsDemoUser)
RETURN u.name AS source, v.name AS target
ORDER BY source, target;
```

Hoặc dùng `CALL` subquery để trả các cột mong muốn. Trên Neo4j 5.23+, `CALL (u) { ... RETURN ... }` khai báo biến import rõ ràng; **không được áp dụng quy tắc import biến của `CALL` sang `EXISTS`**.

| Đặc điểm | `EXISTS { ... }` | `CALL (u) { ... }` (Neo4j 5.23+) |
|---|---|---|
| Mục đích | Kiểm tra có ít nhất một hàng khớp. | Chạy truy vấn con để trả kết quả hoặc thực hiện ghi dữ liệu. |
| Kết quả | Boolean `true`/`false`. | Trả cột/hàng từ `RETURN` hoặc thực hiện ghi. |
| Biến bên ngoài | Tự động nhìn thấy biến trong scope. | Chỉ nhận các biến chỉ định trong `(...)`, hoặc `*`. |
| Biến mới ở trong | Không xuất ra ngoài. | Có thể xuất qua `RETURN`. |
| Số hàng ngoài | Bản thân biểu thức không làm nhân hàng. | Returning subquery có thể tạo 0, 1 hoặc nhiều hàng cho một hàng ngoài. |
| Ghi dữ liệu | Không dùng cho `CREATE`/`MERGE`/`SET`/`DELETE`. | Unit subquery có thể ghi dữ liệu. |

## 8. Dùng `EXISTS` trong `RETURN` và `CASE`

Không bắt buộc phải đặt `EXISTS` trong `WHERE`. Có thể **trả giá trị Boolean như một cột** để ứng dụng xử lý tiếp:

```cypher
MATCH (u:ExistsDemoUser)
RETURN
  u.name AS person,
  EXISTS {
    MATCH (u)-[:FOLLOWS]->(:ExistsDemoUser)
  } AS hasFollowing
ORDER BY person;
```

| person | hasFollowing |
|---|---|
| An | `true` |
| Bình | `true` |
| Chi | `true` |
| Dũng | `false` |

So với ví dụ `WHERE EXISTS` ở trên, `RETURN EXISTS` **giữ cả bốn người** và bổ sung cột trạng thái. Cách này phù hợp cho cờ hiển thị trong API, ví dụ `hasFollowing`, `hasPermission`, `hasUnresolvedIssue`.

Có thể kết hợp với `CASE`:

```cypher
MATCH (u:ExistsDemoUser)
RETURN u.name AS person,
       CASE
         WHEN EXISTS {
           MATCH (u)-[:FOLLOWS]->(:ExistsDemoUser)
         }
         THEN 'Có theo dõi'
         ELSE 'Chưa theo dõi'
       END AS followingStatus
ORDER BY person;
```

Trong ứng dụng Java hoặc Spring Data Neo4j, nên để Cypher trả giá trị Boolean khi cần ánh xạ vào kiểu `boolean`/`Boolean`; dùng chuỗi trạng thái khi đó là yêu cầu hiển thị rõ ràng.

## 9. So sánh `EXISTS`, `MATCH`, `OPTIONAL MATCH`, `COUNT` và `IS NOT NULL`

### 9.1. Chỉ cần biết có mẫu? `EXISTS` tránh nhân số hàng

```cypher
MATCH (u:ExistsDemoUser)
MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
RETURN u.name AS person
ORDER BY person;
```

Kết quả là **An, An, Bình, Chi**. `An` xuất hiện hai lần vì có hai quan hệ `FOLLOWS`. Nếu chỉ muốn tìm người **có** theo dõi, thay `MATCH` thứ hai bằng `WHERE EXISTS` sẽ được **An, Bình, Chi**, mỗi người một hàng.

Có thể dùng `DISTINCT` sau `MATCH` để loại bản sao, nhưng khi không cần bất kỳ dữ liệu nào từ node `v`, `EXISTS` thường mô tả đúng mục tiêu hơn. Neo4j có thể tận dụng kế hoạch truy vấn chuyên biệt cho phép kiểm tra sự tồn tại mà không cần trả tất cả kết quả phù hợp; tốc độ thực tế vẫn cần đo bằng `PROFILE`.

### 9.2. Khi nào cần `COUNT`?

`COUNT` thích hợp để trả lời **có bao nhiêu**, còn `EXISTS` trả lời **có hay không**.

```cypher
MATCH (u:ExistsDemoUser)
OPTIONAL MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
RETURN u.name AS person, count(v) AS followingCount
ORDER BY person;
```

| person | followingCount |
|---|---:|
| An | 2 |
| Bình | 1 |
| Chi | 1 |
| Dũng | 0 |

Nếu cần **số lượng quan hệ** và cờ **có quan hệ**, có thể tính số lượng một lần rồi suy ra `followingCount > 0`. Nếu chỉ cần cờ có/không, `EXISTS` rõ ràng hơn.

Cypher hiện đại còn có **`COUNT { MATCH ... }`** subquery expression để đếm kết quả tương quan; tuy nhiên **không nên thay `EXISTS` bằng `COUNT { ... } > 0` chỉ vì cả hai cùng biểu diễn điều kiện tồn tại**, trừ khi thực sự cần số đếm hoặc có lý do đo đạc cụ thể.

### 9.3. `EXISTS { ... }` có giống kiểm tra thuộc tính tồn tại?

Không hoàn toàn. Có hai câu hỏi:

1. **Một mẫu quan hệ / kết quả truy vấn có tồn tại không?** → `EXISTS { MATCH ... }`.
2. **Một thuộc tính của node/relationship có giá trị khác `null` không?** → `IS NOT NULL`.

Ví dụ kiểm tra thuộc tính của quan hệ:

```cypher
MATCH (u:ExistsDemoUser)-[r:FOLLOWS]->(:ExistsDemoUser)
WHERE r.since IS NOT NULL
RETURN u.name AS person, r.since AS since
ORDER BY person, since;
```

Cú pháp hàm `exists(n.property)` từng xuất hiện trong các tài liệu Neo4j cũ; với Cypher hiện đại, cách viết nên dùng cho thuộc tính là `n.property IS NOT NULL`. Còn `EXISTS { ... }` là một biểu thức truy vấn con dùng để xác minh **có hàng kết quả**.

### 9.4. `OPTIONAL MATCH` khác `NOT EXISTS`

`OPTIONAL MATCH` giữ hàng ngoài ngay cả khi không khớp và điền `null` vào biến của mẫu không khớp. Nó phù hợp để lấy **dữ liệu tùy chọn**, nhưng có thể tạo nhiều hàng khi có nhiều quan hệ khớp. `NOT EXISTS` kiểm tra phủ định và **không sinh biến mới**.

Nếu cần danh sách người không theo dõi ai, dùng `WHERE NOT EXISTS` là cách diễn đạt ngắn và chính xác. Nếu cần tên người được theo dõi hoặc giá trị `null` khi không có, `OPTIONAL MATCH` phù hợp hơn.

## 10. Hiệu năng và cách đọc kế hoạch truy vấn

Với dữ liệu đồ thị lớn, chi phí của điều kiện tồn tại phụ thuộc số node ứng viên, độ chọn lọc của mẫu quan hệ và thuộc tính lọc.

**Ví dụ:**

```cypher
EXPLAIN
MATCH (u:ExistsDemoUser {id: 'an'})
WHERE EXISTS {
  MATCH (u)-[r:FOLLOWS]->(v:ExistsDemoUser)
  WHERE r.since >= 2023
    AND v.active = true
}
RETURN u.name AS person;
```

`EXPLAIN` cho thấy kế hoạch **mà không thực thi** truy vấn. Sau khi hiểu tác động của lệnh, có thể đổi sang `PROFILE` để thu số hàng và số lần truy cập thực tế.

Một số nguyên tắc thực hành:

1. **Thu hẹp node đầu vào trước.** Ví dụ lọc `u.id = $id` trước khi kiểm tra quan hệ. Với tìm kiếm thường xuyên theo `id`, cân nhắc constraint/index thích hợp.
2. **Gắn điều kiện với mẫu bên trong.** Ví dụ `r.since >= $minYear` và `v.active = true` giúp biểu đạt chính xác mẫu cần tìm.
3. **Đừng dùng `MATCH` + `DISTINCT` hoặc `COUNT` chỉ để tìm cờ Boolean nếu `EXISTS` đã đúng ngữ nghĩa.** Việc tạo/tổng hợp nhiều hàng có thể không cần thiết.
4. **Đọc số hàng ở từng bước.** Với mẫu có độ phân nhánh cao hoặc đường đi dài, số khả năng phải xét có thể tăng mạnh. `EXISTS` chỉ trả Boolean, nhưng điều đó **không có nghĩa mọi truy vấn tồn tại đều chạy nhanh**.
5. **Không suy đoán tên operator cố định.** Tùy phiên bản và kế hoạch, có thể thấy các biến thể như `SemiApply`, `AntiSemiApply` hoặc operator khác thực hiện điều kiện tồn tại. Đánh giá bằng `EXPLAIN` và `PROFILE` trên phiên bản đang chạy.

Ví dụ tạo constraint **tùy chọn, chỉ trên database thực hành**:

```cypher
CREATE CONSTRAINT exists_demo_user_id IF NOT EXISTS
FOR (u:ExistsDemoUser)
REQUIRE u.id IS UNIQUE;
```

Constraint uniqueness giúp ngăn nhiều node `:ExistsDemoUser` có cùng giá trị `id` khác `null` và cung cấp khả năng truy cập được index hỗ trợ cho truy vấn tìm theo `id`.

## 11. Lỗi thường gặp

| Vấn đề | Vì sao xảy ra? | Cách sửa |
|---|---|---|
| Một người xuất hiện nhiều lần khi chỉ cần biết có liên kết | Dùng `MATCH` để trả từng quan hệ. | Dùng `WHERE EXISTS { MATCH ... }` để kiểm tra có/không; chỉ dùng `MATCH` khi cần dữ liệu liên kết. |
| `Variable v not defined` ở `RETURN` ngoài | `v` được khai báo bên trong `EXISTS`, không có scope bên ngoài. | Chỉ trả Boolean, hoặc chuyển sang `MATCH`/`CALL` khi cần xuất `v`. |
| `NOT EXISTS` cho kết quả “lạ” | Phủ định **toàn bộ mẫu cùng điều kiện trong subquery**, không chỉ phủ định sự có mặt của relationship. | Viết rõ mẫu trong subquery, kiểm thử bằng ví dụ có quan hệ nhưng không thỏa thuộc tính. |
| Người theo dõi ai đó bị loại dù đã có người phù hợp | Dùng hai `EXISTS` độc lập khi yêu cầu áp dụng cho **cùng node đích**. | Đặt kiểm tra `NOT EXISTS` lồng trong `EXISTS` sau khi ràng buộc biến `v`. |
| So sánh với `null` không ra kết quả | Trong Cypher, `= null` không hoạt động như phép kiểm tra không có giá trị. | Dùng `IS NULL` / `IS NOT NULL` cho thuộc tính. |
| Nhầm `EXISTS` với `CALL` | Cố import bằng `CALL (u)` hoặc trông đợi `EXISTS` trả hàng chi tiết. | `EXISTS` dùng biến ngoài tự động và trả Boolean; `CALL` là một cấu trúc khác. |
| Dùng hàm `exists(n.property)` trong code mới | Cú pháp cũ cho kiểm tra thuộc tính, có thể không tương thích phiên bản Cypher hiện tại. | Thay bằng `n.property IS NOT NULL`. |
| Tin rằng `EXISTS` luôn nhanh | Đường đi dài hoặc dữ liệu thiếu điều kiện lọc vẫn có thể tốn chi phí. | Thu hẹp ứng viên, dùng index khi thích hợp và đo kế hoạch thực tế. |

## 12. Bài tập tự kiểm tra

Dùng dữ liệu mẫu ở mục 2. Hãy thử tự viết truy vấn trước khi xem đáp án.

**Bài 1.** Tìm người có theo dõi ít nhất một người **không hoạt động**.

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE v.active = false
}
RETURN u.name AS person
ORDER BY person;
```

Kỳ vọng: **An, Bình**.

**Bài 2.** Tìm người có theo dõi người không hoạt động, nhưng **không theo dõi người đang hoạt động**.

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE v.active = false
}
AND NOT EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE v.active = true
}
RETURN u.name AS person
ORDER BY person;
```

Kỳ vọng: **Bình**. `Dũng` không có người theo dõi nên không thỏa vế `EXISTS` thứ nhất.

**Bài 3.** Tìm người **đã chặn một người mình đang theo dõi**.

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  MATCH (u)-[:BLOCKS]->(v)
}
RETURN u.name AS person;
```

Kỳ vọng: **An** — người đã theo dõi và chặn Chi.

## 13. Tổng kết

- `EXISTS { ... }` kiểm tra truy vấn con có **ít nhất một kết quả** và trả `true`/`false`; nó không xuất biến bên trong hay làm nhân hàng ở truy vấn ngoài.
- `NOT EXISTS { ... }` kiểm tra **không có kết quả thỏa toàn bộ mẫu và điều kiện** — đặc biệt hữu ích cho truy vấn phủ định trên quan hệ.
- Biến ngoài được dùng **trực tiếp** trong existential subquery; chỉ biến được xác định ở ngoài mới có thể tiếp tục dùng ở `RETURN` bên ngoài.
- Dùng `EXISTS` khi mục tiêu là **có/không**; dùng `MATCH` khi muốn lấy node/relationship, `COUNT` khi cần số lượng và `IS NOT NULL` khi kiểm tra sự có mặt của thuộc tính.
- Với mạng liên kết có nhiều bước, đặt toàn bộ mẫu và điều kiện tương quan trong một `EXISTS`; lồng `NOT EXISTS` khi cần kiểm tra phủ định áp dụng cho **cùng biến đích**.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — EXISTS subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/existential/) — cú pháp tồn tại, tương quan biến và các trường hợp sử dụng.
- [Neo4j Cypher Manual — WHERE](https://neo4j.com/docs/cypher-manual/current/clauses/where/) — dùng biểu thức Boolean để lọc mẫu.
- [Neo4j Cypher Manual — Predicates](https://neo4j.com/docs/cypher-manual/current/expressions/predicates/) — các phép so sánh, `IS NULL` và `IS NOT NULL`.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/) — đọc `EXPLAIN` và `PROFILE` để phân tích hiệu năng.

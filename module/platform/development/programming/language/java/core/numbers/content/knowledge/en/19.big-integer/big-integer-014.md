# Probabilistic Primality Testing and the Meaning of `certainty` with `BigInteger`

> **Java core – numbers · BigInteger**  
> **Goal:** Understand the result of `BigInteger.isProbablePrime(int certainty)`, how to interpret probabilistic error bounds, edge cases (especially `certainty <= 0`), and the difference between testing a candidate, generating a probable prime, and proving primality. Uses Java 17+.

## 1. Prime Numbers and Why Probabilistic Algorithms Are Needed

A prime number is a **positive integer greater than 1** with exactly two positive divisors: 1 and itself. For example, 2, 3, 5, 7, 11, 17, and 97 are prime; 0, 1, −17, 21, and 561 are not prime by that definition.

For small numbers, you can try dividing by integers from 2 up to the square root of `n`. Yet a `BigInteger` can hold numbers hundreds or thousands of bits long. Trying all small divisors in that range is far too expensive. Java provides a fast probabilistic test:

```java
import java.math.BigInteger;

BigInteger n = new BigInteger("1000000007");
boolean probable = n.isProbablePrime(80);

System.out.println(probable); // true
```

The name **isProbablePrime** is very deliberate: the method does not return an unconditional exact primality proof. It tests the candidate to a confidence level supplied by the caller.

Three easily confused operations:

| Question | API |
| --- | --- |
| Is an existing value `n` likely prime? | `n.isProbablePrime(certainty)` |
| Generate a positive random value of exact `k` bits that is probably prime? | `BigInteger.probablePrime(k, rnd)` |
| Find the first probable prime greater than `n`? | `n.nextProbablePrime()` |

In strict applications, distinguish a **probable prime** from a **proven prime**: a probabilistic test does not produce a certificate for third parties to verify `n` is prime.

## 2. Signature and Two Asymmetric Conclusions

Signature in `java.math.BigInteger`:

```java
public boolean isProbablePrime(int certainty)
```

When `certainty > 0`:

- `false`: the number is **definitely composite** per the Javadoc contract; the test has eliminated the candidate.
- `true`: the number is **probably prime** to the confidence level tied to the `certainty` parameter; not yet an absolute mathematical proof.

Example:

```java
System.out.println(BigInteger.valueOf(17)
        .isProbablePrime(80)); // true
System.out.println(BigInteger.valueOf(21)
        .isProbablePrime(80)); // false
```

Do not invert the meaning into "`false` is *probably composite* while `true` is *definitely prime*." The right mental model is: if composite evidence is found, reject immediately; if none is found, treat it as a prime candidate per the algorithm's probability guarantee.

**Input precondition:** because primality applies only to `n ≥ 2`, a business method should check this condition even if the JDK implementation has rules for negative numbers.

## 3. What Does `certainty` Represent?

Java 17 Javadoc describes `certainty` as **the measure of uncertainty the caller is willing to tolerate**. When `isProbablePrime(certainty)` returns `true`, the documentation states the probability that `n` is prime exceeds:

\[
1 - \frac{1}{2^{\mathrm{certainty}}}.
\]

Under the API model's error-bound interpretation, the remaining risk is expressed by `2^-certainty`. Larger `certainty` demands higher confidence and generally costs more computation.

| certainty | `2^-certainty` (approx.) |
| ---: | ---: |
| 1 | 0.5 |
| 10 | 9.77×10^-4 |
| 20 | 9.54×10^-7 |
| 40 | 9.09×10^-13 |
| 80 | 8.27×10^-25 |
| 100 | 7.89×10^-31 |
| 128 | 2.94×10^-39 |

For example, passing 80 expresses a high confidence level, not a demand for exact 80 test rounds.

### Do Not Equate the Probability Bound with the Posterior Probability of a Fixed Number

A given integer `n` is **either prime or composite**. Once `n` is fixed, that property does not turn into a frequentist probability. Uncertainty comes from the choice of test algorithm, probabilistic assumptions, and candidate distribution. Therefore, do not say:

> "The exact mathematical probability that `n=...` is prime equals `1−2^-80`."

That is not an automatically valid Bayesian inference for arbitrary adversarially chosen `n`. The proper phrasing in software design is **relying on the API's probabilistic guarantee when the test returns probable prime**, while also evaluating candidate generation policy and system risk model.

### `certainty` Is NOT the Number of Miller–Rabin Rounds

`certainty=80` does not guarantee **exactly 80 rounds** of Miller–Rabin. The actual round count and supplementary tests depend on the implementation, bit length of the number, and optimizations. Never write code assuming "`certainty` is literally the iteration count."

Use `certainty` as a quality parameter, not an exact loop-control or runtime-control parameter. For algorithm auditing requirements, consult specific specifications or implementations rather than guessing from the signature.

## 4. The Biggest Pitfall: `certainty <= 0` Always Returns `true`

The Javadoc explicitly specifies: if `certainty <= 0`, `isProbablePrime` returns **`true`**, regardless of the tested value.

```java
BigInteger nine = BigInteger.valueOf(9);

System.out.println(nine.isProbablePrime(0));   // true
System.out.println(nine.isProbablePrime(-5));  // true
System.out.println(nine.isProbablePrime(80));  // false
```

The number 9 is still composite `3×3`. The `true` results of the first two calls **do not prove** or even give useful confidence about primality.

```java
System.out.println(BigInteger.ZERO.isProbablePrime(0)); // true
System.out.println(BigInteger.ONE.isProbablePrime(-1)); // true
```

**Never pass 0 or a negative number expecting Java to pick a default level.** If `certainty` is read from config, env vars, HTTP parameters, or a database, validate `certainty > 0` before calling the API.

A clear-intent helper:

```java
static boolean probablyPrimePositive(BigInteger n, int certainty) {
    if (certainty <= 0) {
        throw new IllegalArgumentException("certainty must be positive");
    }
    if (n == null || n.compareTo(BigInteger.TWO) < 0) {
        return false;
    }
    return n.isProbablePrime(certainty);
}
```

This is an **illustrative method** to be placed inside a class. The null policy can be designed to throw instead of returning `false`; what matters is documenting it clearly in the API.

## 5. Negative Numbers, 0, 1, 2, and Edge Cases

By definition of primality:

| n | Is it prime? |
| ---: | --- |
| −17 | No |
| −2 | No |
| 0 | No |
| 1 | No |
| 2 | Yes |
| 3 | Yes |
| 4 | No |
| 17 | Yes |
| 21 | No |

With positive `certainty`, common cases:

```java
System.out.println(BigInteger.ZERO.isProbablePrime(80)); // false
System.out.println(BigInteger.ONE.isProbablePrime(80));  // false
System.out.println(BigInteger.TWO.isProbablePrime(80));  // true
System.out.println(BigInteger.valueOf(100).isProbablePrime(80)); // false
```

### Why Check `n ≥ 2` Before Calling the API?

In OpenJDK 17, the `isProbablePrime` implementation takes the **absolute value** when testing:

```java
BigInteger negative = BigInteger.valueOf(-17);
System.out.println(negative.isProbablePrime(80));
// true on OpenJDK 17
```

Magnitude 17 is prime, yet **−17 is not a positive prime**. Never take raw boolean results from this API as business decisions before enforcing the valid domain.

```java
boolean accepted = negative.compareTo(BigInteger.TWO) >= 0
        && negative.isProbablePrime(80);

System.out.println(accepted); // false
```

Handling of negative values can be an implementation detail; by validating `n ≥ 2`, your code does not depend on that behavior to define primality.

## 6. Comparison with Deterministic Trial Division for Small Numbers

A **deterministic** check for small `long` numbers:

```java
static boolean trialPrime(long n) {
    if (n < 2) return false;
    if ((n & 1L) == 0L) return n == 2;
    for (long d = 3; d <= n / d; d += 2) {
        if (n % d == 0L) {
            return false;
        }
    }
    return true;
}
```

The function tests odd divisors up to √n. The condition `d <= n/d` is safer than `d*d <= n` because multiplication can overflow at large `long` values. If a divisor is found, `n` is composite; if none is found, `n` is prime.

```java
System.out.println(trialPrime(97));  // true
System.out.println(trialPrime(561)); // false
```

Drawback: for numbers near the `long` limit, trial division can be slow; for a `BigInteger` hundreds of bits long, brute-force trial division is infeasible. That is why modern primality tests use modular arithmetic and probabilistic strategies.

**Purpose of trial division here:** as a small trustworthy oracle when testing the probable-prime API, not as a way to generate cryptographic key-sized primes.

## 7. Fermat and Carmichael Number 561: Why a Simple Test Is Not Enough

Fermat's Little Theorem states: if `p` is prime and `a` is not divisible by `p`, then:

\[
a^{p-1} \equiv 1 \pmod p.
\]

Java provides `modPow` to compute modular exponentiation efficiently without building a huge `a^(p−1)` before dividing:

```java
BigInteger n = BigInteger.valueOf(561);
BigInteger residue = BigInteger.TWO.modPow(
        n.subtract(BigInteger.ONE), n);

System.out.println(residue); // 1
```

If someone naively used a Fermat check, they might think 561 is prime. Yet:

\[
561 = 3\times11\times17.
\]

561 is a **Carmichael composite number**. It passes Fermat tests for many bases, so a result `a^(n−1) mod n = 1` **is not enough to prove `n` prime**.

```java
System.out.println(
        BigInteger.valueOf(561).isProbablePrime(80)); // false
```

Java's probable-prime algorithm is stronger than a single-base Fermat check in this example. However, **do not infer** that every other composite is guaranteed to be caught by every probabilistic test with finite `certainty`.

## 8. Intuition Behind Miller–Rabin: Finding Composite Witnesses

An important probabilistic primality technique is *Miller–Rabin*. For an odd number `n>2`, decompose:

\[
n-1 = 2^s d,\quad d\text{ odd}.
\]

Then pick a base `a` and compute modular powers/squarings modulo `n`. If the sequence violates properties required of primes, a **composite witness** is found.

- Composite witness found → eliminate candidate.
- No witness found across tests → candidate is a *probable prime* under the test used.
- More rounds/appropriate testing strategies lower the risk of a composite slipping through.
- A passing result **does not automatically produce a primality certificate**.

You do not need to implement Miller–Rabin yourself to use `BigInteger.isProbablePrime`. Self-implementations easily make mistakes on `n=2`, even `n`, factoring `n−1`, base selection, modular operations, and randomness.

The JDK may combine testing steps and small-prime sieving depending on the version. Thus avoid stating "`BigInteger.isProbablePrime` is guaranteed to run only one specific algorithm and exact N rounds" when the API makes no such promise.

## 9. Choosing `certainty`: Confidence, Cost, and Business Risk

Higher `certainty` gives stronger checking guarantees and usually higher cost. No single value fits every system.

For example, an application might choose:

```java
private static final int PRIME_CERTAINTY = 100;
```

Yet `100` is merely an **illustrative value** with high confidence; it does not by itself guarantee an entire key-generation workflow meets a specific cryptographic standard.

Decide based on:

1. **Consequence if a composite number is accepted.**
2. **Number of candidates** the system accepts over its lifetime.
3. **Bit length** of candidates and CPU/memory cost.
4. **Audit requirements:** is a probable prime sufficient, or is a primality certificate needed?
5. **Candidate generation source and distribution**, especially if data can be adversarially crafted.
6. **JDK version, libraries, or technical standards** that must be followed.

Many calls in a service create a **cumulative risk** problem. Do not assume repeating `n` times always gives exact error probability `n×2^-certainty` or independent trials; examine assumptions about the events. In conservative arguments, a *union bound* can bound error when preconditions hold.

**Do not set an arbitrarily huge `certainty`** aiming for "absolute certainty": probabilistic testing does not become a proof merely from a large parameter, while resource costs can climb.

## 10. `isProbablePrime` Checks; `probablePrime` Generates Candidates

Two similar-looking calls serve two distinct goals:

```java
// Test an existing n:
boolean checked = n.isProbablePrime(80);

// Generate a random 64-bit probable prime candidate:
BigInteger generated = BigInteger.probablePrime(
        64, new java.security.SecureRandom());
```

`BigInteger.probablePrime(int bitLength, Random rnd)` returns a **positive number of the exact requested bit length** that is a probable prime. Java 17 Javadoc specifies the probability the generated number is composite **does not exceed `2^-100`**.

- `bitLength` must be `≥ 2` and within implementation limits.
- Specific values depend on the random source; never assert a fixed numeric stdout for it.
- The parameter type is `Random`, yet when generating keys, use `SecureRandom`.
- The API generates only a *probable prime*, not a primality-proof certificate.

In Java:

```java
import java.math.BigInteger;
import java.security.SecureRandom;

SecureRandom random = new SecureRandom();
BigInteger p = BigInteger.probablePrime(64, random);

System.out.println(p.bitLength()); // 64
System.out.println(p.signum() > 0); // true
System.out.println(p.testBit(0));   // true: a 64-bit prime is odd
```

These three properties remain stable even though the random value `p` changes on every run.

## 11. Three Easily Confused Constructors/Factories

| Creation method | Meaning |
| --- | --- |
| `BigInteger.probablePrime(64, rnd)` | Generates a positive probable prime of exact 64 bits |
| `new BigInteger(64, 100, rnd)` | Generates a positive probable prime of exact 64 bits, certainty 100 |
| `new BigInteger(64, rnd)` | Generates a random non-negative number of at most 64 bits; **does not promise prime** |

Three-argument constructor:

```java
BigInteger p = new BigInteger(
        64, 100, new SecureRandom());
```

allows specifying `certainty`. Javadoc recommends **using `probablePrime`** unless there is a specific reason to specify `certainty` yourself.

Two-argument constructor:

```java
BigInteger randomBits = new BigInteger(
        64, new SecureRandom());
```

only produces a non-negative random number; it can be even, less than 2, and entirely composite. **Never** treat it as a probable prime.

Specifically, with the random-bits constructor, the requested bit count is an **upper bound**, not guaranteeing `bitLength() == 64`; the highest bit can be 0.

## 12. `nextProbablePrime`: Finding the First Candidate Greater Than `n`

Another utility method:

```java
BigInteger start = BigInteger.valueOf(100);
BigInteger next = start.nextProbablePrime();

System.out.println(next); // 101
```

`nextProbablePrime()` finds a probable prime **strictly greater than** `n`, excluding `n` itself:

```java
System.out.println(
        BigInteger.valueOf(2).nextProbablePrime()); // 3
```

Java 17 Javadoc states the probability bound of being composite does not exceed `2^-100` for the returned result; at the same time, the method **never skips over an actual prime** between `n` and the result.

For negative numbers, Java throws `ArithmeticException`:

```java
try {
    BigInteger.valueOf(-5).nextProbablePrime();
} catch (ArithmeticException ex) {
    System.out.println("negative search rejected");
}
```

Do not confuse with `isProbablePrime`: one **classifies the current number**, while the other **searches for a larger candidate**.

### Randomness Cannot Be Inferred from `nextProbablePrime`

If the input `start` is predictable, `nextProbablePrime()` also yields a predictable result. Never use the next-prime finder to automatically generate unpredictable cryptographic keys without a randomized candidate-selection process and full key validation.

## 13. `SecureRandom` Matters When Generating Primes for Cryptography

The probable-prime generation APIs accept a `Random`, yet not every `Random` meets security standards:

```java
import java.util.Random;
import java.security.SecureRandom;

// For non-cryptographic demo only:
// Random predictable = new Random(123);

// When using for sensitive applications:
SecureRandom secure = new SecureRandom();
BigInteger prime = BigInteger.probablePrime(128, secure);
```

Regular `Random` is not a cryptographic random number generator. Fixed seeds make outputs reproducible and predictable; unsuitable when generated numbers must remain secret.

**A probable prime is not yet a complete RSA key.** RSA workflows also require key sizes, public exponents, relationships between primes `p`/`q`, key calculations, secret protection, standard checks, and implementation-bug defenses. In real software, use `KeyPairGenerator` or a vetted cryptographic library.

Never log seeds, `p`, `q`, or secret key material. Lessons should print only **non-sensitive properties** of generated values.

## 14. Accepting Untrusted Input Data

Do not accept a million-character decimal string and a huge `certainty` and immediately call `isProbablePrime` inside an HTTP request without bounds.

Practical safeguards:

- Limit **numeric string length** before parsing.
- Validate syntax with `BigInteger(String)` and handle `NumberFormatException`.
- Bound `n.bitLength()` to fit the problem.
- Ensure `n >= 2` before treating a value as a prime candidate.
- Ensure `certainty > 0` and no larger than the policy cap.
- Bound processing time, concurrent calls, CPU, and memory.
- Clearly distinguish invalid input, composite, and probable prime states; never collapse them into one misleading boolean.

Example helper:

```java
static boolean boundedPrimalityTest(
        BigInteger n, int certainty, int maxBits) {
    if (n == null || certainty <= 0 || maxBits < 2) {
        throw new IllegalArgumentException("Invalid input/policy");
    }
    if (n.compareTo(BigInteger.TWO) < 0) {
        return false;
    }
    if (n.bitLength() > maxBits) {
        throw new IllegalArgumentException("Too many bits");
    }
    return n.isProbablePrime(certainty);
}
```

This is an illustrative method. `maxBits` is a business limit, not a fixed intrinsic `BigInteger` boundary. Production also needs separate policies for input strings, logging, and resource limits.

## 15. Complete Java 17+ Program

Create file **`BigIntegerPrimalityDemo.java`**:

```java
import java.math.BigInteger;
import java.security.SecureRandom;
import java.util.List;
import java.util.Objects;

public class BigIntegerPrimalityDemo {
    private static final int CERTAINTY = 80;

    private static boolean acceptable(BigInteger n, int certainty) {
        Objects.requireNonNull(n, "candidate");
        if (certainty <= 0) {
            throw new IllegalArgumentException(
                    "certainty must be positive");
        }
        if (n.compareTo(BigInteger.TWO) < 0) {
            return false;
        }
        return n.isProbablePrime(certainty);
    }

    private static boolean trialPrime(long n) {
        if (n < 2) return false;
        if ((n & 1L) == 0L) return n == 2;

        for (long d = 3; d <= n / d; d += 2) {
            if (n % d == 0) return false;
        }
        return true;
    }

    public static void main(String[] args) {
        for (String text : List.of(
                "0", "1", "2", "17", "21", "561", "1000000007")) {
            BigInteger n = new BigInteger(text);
            boolean result = acceptable(n, CERTAINTY);
            System.out.println(text + " -> "
                    + (result ? "probably prime" : "composite"));
        }

        BigInteger nine = BigInteger.valueOf(9);
        System.out.println("certainty 0 for 9 = "
                + nine.isProbablePrime(0));
        System.out.println("certainty -3 for 0 = "
                + BigInteger.ZERO.isProbablePrime(-3));

        try {
            acceptable(nine, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("validated certainty = rejected");
        }

        BigInteger negative = BigInteger.valueOf(-17);
        System.out.println("negative -17 raw test = "
                + negative.isProbablePrime(CERTAINTY));
        System.out.println("negative -17 validated = "
                + acceptable(negative, CERTAINTY));

        BigInteger n561 = BigInteger.valueOf(561);
        BigInteger fermat = BigInteger.TWO.modPow(
                n561.subtract(BigInteger.ONE), n561);
        System.out.println("Fermat 2^560 mod 561 = " + fermat);

        System.out.println("trial division 97 = " + trialPrime(97));
        System.out.println("trial division 561 = " + trialPrime(561));
        System.out.println("next probable after 100 = "
                + BigInteger.valueOf(100).nextProbablePrime());

        try {
            BigInteger.valueOf(-5).nextProbablePrime();
        } catch (ArithmeticException ex) {
            System.out.println("negative search = rejected");
        }

        SecureRandom rnd = new SecureRandom();
        BigInteger generated = BigInteger.probablePrime(64, rnd);
        System.out.println("generated bit length = "
                + generated.bitLength());
        System.out.println("generated positive odd = "
                + (generated.signum() > 0 && generated.testBit(0)));
    }
}
```

Run in an environment with JDK 17 or later:

```bash
javac --release 17 BigIntegerPrimalityDemo.java
java BigIntegerPrimalityDemo
```

**Expected stdout on OpenJDK 17 (random section prints only stable properties):**

```text
0 -> composite
1 -> composite
2 -> probably prime
17 -> probably prime
21 -> composite
561 -> composite
1000000007 -> probably prime
certainty 0 for 9 = true
certainty -3 for 0 = true
validated certainty = rejected
negative -17 raw test = true
negative -17 validated = false
Fermat 2^560 mod 561 = 1
trial division 97 = true
trial division 561 = false
next probable after 100 = 101
negative search = rejected
generated bit length = 64
generated positive odd = true
```

### Explaining the Output

1. 0 and 1 are not prime; 2 and 17 are prime; 21 and 561 are composite.
2. Non-positive `certainty` makes `isProbablePrime` return `true` even for composites; the validated wrapper rejects that case.
3. OpenJDK may test the magnitude of −17 and return `true`; the wrapper requires `n≥2` so it returns `false`.
4. Carmichael 561 yields `2^560 mod 561 = 1` despite being composite; high-certainty probable prime testing still identifies it as composite.
5. `nextProbablePrime` returns 101 when searching above 100; negative arguments to this method are rejected.
6. `SecureRandom` produces non-fixed values, yet `probablePrime(64,...)` guarantees exact 64 bits and a 64-bit prime candidate must be odd.

## 16. Common Misconceptions

| Misconception | Truth |
| --- | --- |
| "`isProbablePrime(100) == true` is a prime proof" | It is probably prime to the API's confidence level |
| "`false` is only probably composite" | With `certainty>0`, Javadoc says `false` is definitely composite |
| "`certainty` 0 requests a default" | `certainty≤0` returns `true` immediately |
| "`certainty` 80 is exact 80 Miller–Rabin rounds" | The API does not guarantee a specific round count |
| "Reading `2^-80` gives the exact posterior probability for a fixed `n`" | Must consider probabilistic/candidate model, not interpret mechanically |
| "Negative numbers are never accepted by `isProbablePrime` by default" | OpenJDK may test absolute value; check `n≥2` yourself |
| "1 is prime because it has no small divisors" | 1 is not prime by definition |
| "Fermat `a^(n−1) mod n = 1` proves prime" | Carmichael composites like 561 exist |
| "`probablePrime` and `isProbablePrime` do the same thing" | One generates, one tests |
| "`new BigInteger(64, rnd)` generates a probable prime" | That constructor generates a non-negative random number, possibly composite |
| "`nextProbablePrime` can return the input number itself" | Returns a number strictly greater than `n` |
| "Repeated calls to `isProbablePrime` are always independent trials" | The API makes no such guarantee |
| "`SecureRandom` by default guarantees compliant RSA generation" | Full key workflow and standards are required |
| "Increasing `certainty` infinitely turns probability into proof" | No, it remains a probabilistic check per contract |
| "`BigInteger` eliminates all DoS risks" | CPU, RAM, and implementation limits are still finite |

## 17. Self-Check Exercises and Solutions

**Exercise 1.** What does `BigInteger.valueOf(9).isProbablePrime(0)` return? Does it make 9 prime?  
**Answer:** Returns `true` because `certainty≤0`; 9 is still composite. Validation is needed.

**Exercise 2.** What do `BigInteger.ONE.isProbablePrime(80)` and `BigInteger.TWO.isProbablePrime(80)` return?  
**Answer:** `false` and `true` respectively because 1 is not prime and 2 is prime.

**Exercise 3.** Why should you not assume `certainty=80` runs exact 80 Miller–Rabin rounds?  
**Answer:** `certainty` expresses requested confidence; algorithms, round counts, and extra steps are implementation details.

**Exercise 4.** Why does `2^560 mod 561=1` not prove 561 is prime?  
**Answer:** `561=3×11×17`, a Carmichael number passing the base-2 Fermat check.

**Exercise 5.** Explain the difference between `BigInteger.probablePrime(64,rnd)` and `new BigInteger(64,rnd)`.  
**Answer:** The first generates a positive probable prime of exact 64 bits; the second generates a non-negative number of at most 64 bits, possibly composite.

**Exercise 6.** If primes are needed for RSA, why is merely calling `isProbablePrime(100)` insufficient?  
**Answer:** You need a secure random source, `p`/`q` selection, key parameters, standard compliance checks, and a secure cryptographic library.

**Exercise 7.** What does `BigInteger.valueOf(100).nextProbablePrime()` return?  
**Answer:** 101, because it seeks a probable prime **greater than** 100.

**Exercise 8.** An application must test positive primes, yet `n=−17`. What is the business-correct result?  
**Answer:** `false`; enforce `n≥2` before calling probable-prime even though the implementation may test absolute value.

**Exercise 9.** If `isProbablePrime(100)` returns `false` for `n≥2`, should you retry 100 times to prove `n` prime?  
**Answer:** No. `false` means `n` was detected as composite per the API; retrying will not reverse mathematical nature.

**Exercise 10.** When an independently verifiable primality certificate is required, is a `true` return value enough?  
**Answer:** No. A proper primality-proving algorithm and verifiable certificate are needed.

**Exercise 11.** Why must input `certainty` be capped, even though higher `certainty` sounds good?  
**Answer:** CPU/cost can grow and attackers could request enormous checking levels; values must follow policy.

**Exercise 12.** When output from `probablePrime(64,new SecureRandom())` changes on each run, is that a bug?  
**Answer:** No. That is normal random behavior; verify `bitLength()==64`, positive, and odd rather than comparing against a fixed number.

## 18. Checklist When Applying in Real Programs

1. **Identify requirements:** is a probable prime sufficient, or is a primality proof mandatory?
2. **Validate `n ≥ 2`** to obey the positive-prime definition.
3. **Validate `certainty > 0`**; never use 0 or negative as a default.
4. **Read `true`/`false` accurately:** `true` is probable; `false` is composite per contract.
5. **Do not equate `certainty` with Miller–Rabin round count.**
6. **Do not mechanically interpret the `2^-certainty` bound** as an absolute posterior probability for arbitrary `n`.
7. **Test boundary values:** negatives, 0, 1, 2, evens, 561, known primes.
8. **Distinguish checking, generating, and searching APIs:** `isProbablePrime`, `probablePrime`, and `nextProbablePrime`.
9. **For cryptographic data:** use `SecureRandom` and standard key-generation APIs/protocols.
10. **Bound resources:** input length, `bitLength`, `certainty`, and processing time.
11. **Avoid printing randomly generated prime values in reference stdout**; print only stable properties.
12. **When proof is required:** use a dedicated primality-proving algorithm and verification certificate.

### References

- [BigInteger — Javadoc Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html)
- [SecureRandom — Javadoc Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html)
- [Random — Javadoc Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html)

**Key takeaway:** `BigInteger.isProbablePrime(certainty)` performs a **probabilistic** check and does not supply a primality certificate. For positive `certainty`, `false` means composite; `true` means probable prime to the API's confidence level. For `certainty≤0`, the method **returns `true` immediately**, so parameter validation is mandatory. Generating candidates for security purposes also requires proper randomness sources and key-management workflows.